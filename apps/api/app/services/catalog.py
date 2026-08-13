"""Sync model catalogs from provider APIs; expose only usable models."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.llm.registry import PROVIDER_PRESETS, build_provider
from app.models import ModelCatalogItem, ModelProvider, ProviderCredential
from app.security.crypto import decrypt_secret

logger = logging.getLogger(__name__)
settings = get_settings()

# Fake offline catalog entries — never offer these in Model Selector.
PLACEHOLDER_TAG = "placeholder"


async def ensure_provider_presets(db: AsyncSession) -> list[ModelProvider]:
    existing = (await db.execute(select(ModelProvider))).scalars().all()
    by_name = {p.name: p for p in existing}
    result = []
    for preset in PROVIDER_PRESETS:
        if preset["name"] in by_name:
            result.append(by_name[preset["name"]])
            continue
        provider = ModelProvider(
            name=preset["name"],
            type=preset["type"],
            base_url=preset["base_url"],
            capabilities_json=preset["capabilities_json"],
            is_active=True,
        )
        db.add(provider)
        result.append(provider)
    await db.flush()
    return result


async def disable_all_placeholders(db: AsyncSession) -> int:
    result = await db.execute(select(ModelCatalogItem))
    count = 0
    for item in result.scalars().all():
        if _is_placeholder_item(item):
            if item.is_enabled:
                item.is_enabled = False
                count += 1
            tags = list(item.tags or [])
            if PLACEHOLDER_TAG not in tags:
                tags.append(PLACEHOLDER_TAG)
                item.tags = tags
    if count:
        await db.flush()
    return count


def _is_placeholder_item(item: ModelCatalogItem) -> bool:
    tags = item.tags or []
    if PLACEHOLDER_TAG in tags:
        return True
    mid = (item.model_id or "").lower()
    # Historical/demo rows use multiple naming schemes. Be conservative:
    # if it looks like a demo and contains a path separator, treat it as placeholder.
    if "/" in mid:
        if mid.endswith(("/free-demo", "/balanced", "/quality")):
            return True
        if any(
            k in mid
            for k in (
                "free-demo",
                "/balanced",
                "/quality",
                "demo",
                "balanced",
                "quality",
            )
        ):
            # Avoid accidentally disabling non-demo models that just contain a word.
            # Those usually don't use "demo"/"balanced"/"quality" as structural path parts.
            return True

    # Sometimes demo rows are only marked via tags.
    lowered_tags = {str(t).lower() for t in tags}
    return bool(
        lowered_tags.intersection({"demo", "placeholder", "balanced", "quality", "free-demo"})
    )


async def provider_has_key(db: AsyncSession, provider: ModelProvider) -> bool:
    return bool(await _key_for_provider(db, provider))


async def list_usable_models(db: AsyncSession) -> list[ModelCatalogItem]:
    """
    Models that can actually be called:
    - enabled
    - not placeholders
    - provider has BYOK or env API key
    """
    await ensure_provider_presets(db)
    await disable_all_placeholders(db)

    providers = (await db.execute(select(ModelProvider).where(ModelProvider.is_active.is_(True)))).scalars().all()
    usable_provider_ids: set[UUID] = set()
    for p in providers:
        if await provider_has_key(db, p):
            usable_provider_ids.add(p.id)

    if not usable_provider_ids:
        return []

    result = await db.execute(
        select(ModelCatalogItem)
        .where(
            ModelCatalogItem.is_enabled.is_(True),
            ModelCatalogItem.provider_id.in_(usable_provider_ids),
        )
        .options(selectinload(ModelCatalogItem.provider))
    )
    models = []
    for m in result.scalars().all():
        if _is_placeholder_item(m):
            continue
        models.append(m)
    return models


async def sync_provider_models(
    db: AsyncSession, provider_id: UUID, api_key: str | None = None
) -> list[ModelCatalogItem]:
    provider = await db.get(ModelProvider, provider_id)
    if provider is None:
        raise ValueError("Provider not found")

    key = api_key or await _key_for_provider(db, provider)
    adapter = build_provider(
        provider.type, provider.name, provider.base_url, provider.capabilities_json
    )

    remote = []
    if key:
        try:
            remote = await adapter.list_models(key)
            logger.info("Synced %s models from %s", len(remote), provider.name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Catalog sync failed for %s: %s", provider.name, exc)

    existing = (
        await db.execute(
            select(ModelCatalogItem).where(ModelCatalogItem.provider_id == provider.id)
        )
    ).scalars().all()
    by_mid = {m.model_id: m for m in existing}

    # Without a real catalog, do NOT invent fake models — disable old placeholders.
    if not remote:
        for item in existing:
            if _is_placeholder_item(item):
                item.is_enabled = False
        await db.flush()
        return []

    remote_ids = {info.model_id for info in remote}
    upserted: list[ModelCatalogItem] = []
    for info in remote:
        item = by_mid.get(info.model_id)
        if item is None:
            item = ModelCatalogItem(provider_id=provider.id, model_id=info.model_id, label=info.label)
            db.add(item)
        item.label = info.label
        item.is_free = info.is_free
        item.input_price = info.input_price
        item.output_price = info.output_price
        item.context_window = info.context_window
        item.capabilities_json = info.capabilities
        # Drop placeholder tag if this was previously a fake row reused somehow
        tags = [t for t in (info.tags or []) if t != PLACEHOLDER_TAG]
        item.tags = tags
        item.is_enabled = True
        upserted.append(item)

    # Disable local placeholders and stale demo rows not in remote catalog
    for item in existing:
        if _is_placeholder_item(item) or item.model_id not in remote_ids:
            if _is_placeholder_item(item):
                item.is_enabled = False
            # Keep real remote-synced models that disappeared? disable if not in remote
            if item.model_id not in remote_ids:
                item.is_enabled = False

    await db.flush()
    return upserted


async def _key_for_provider(db: AsyncSession, provider: ModelProvider) -> str:
    result = await db.execute(
        select(ProviderCredential).where(
            ProviderCredential.provider_id == provider.id,
            ProviderCredential.is_active.is_(True),
        ).limit(1)
    )
    cred = result.scalar_one_or_none()
    if cred:
        return decrypt_secret(cred.encrypted_secret)
    # Important UX contract:
    # - Model Selector should be empty until the user adds a BYOK credential.
    # - Local env keys (settings.*_api_key) must not automatically unlock models.
    return ""

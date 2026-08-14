from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.llm.recommendations import STEP_RECOMMENDATIONS, rank_models_for_step
from app.llm.base import GenerateRequest
from app.llm.registry import build_provider
from app.models import ModelCatalogItem, ModelProvider, ProviderCredential, StepModelConfig, User, UserModel
from app.schemas import (
    CredentialCreate,
    CredentialOut,
    ModelOut,
    ModelAddIn,
    ProviderCreate,
    ProviderOut,
    ProviderTestRequest,
    StepModelConfigIn,
    StepModelConfigOut,
    UserModelCreate,
    UserModelKeyUpdate,
    UserModelOut,
    UserModelTestOut,
)
from app.security.crypto import decrypt_secret, encrypt_secret
from app.services.catalog import (
    ensure_provider_presets,
    list_usable_models,
    sync_provider_models,
    provider_has_key,
)

router = APIRouter(tags=["providers"])


def _model_out(m: ModelCatalogItem) -> ModelOut:
    data = ModelOut.model_validate(m)
    if getattr(m, "provider", None) is not None:
        data.provider_name = m.provider.name
    return data


@router.get("/providers", response_model=list[ProviderOut])
async def list_providers(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await ensure_provider_presets(db)
    result = await db.execute(select(ModelProvider).order_by(ModelProvider.name))
    return result.scalars().all()


@router.post("/providers", response_model=ProviderOut)
async def create_provider(
    body: ProviderCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    provider = ModelProvider(**body.model_dump())
    db.add(provider)
    await db.flush()
    await db.refresh(provider)
    return provider


@router.post("/providers/credentials", response_model=CredentialOut)
async def add_credential(
    body: CredentialCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    provider = await db.get(ModelProvider, body.provider_id)
    if provider is None:
        raise HTTPException(404, "Provider not found")

    # Deactivate previous keys for this user+provider, keep one active.
    prev = await db.execute(
        select(ProviderCredential).where(
            ProviderCredential.owner_id == user.id,
            ProviderCredential.provider_id == body.provider_id,
            ProviderCredential.is_active.is_(True),
        )
    )
    for old in prev.scalars().all():
        old.is_active = False

    cred = ProviderCredential(
        owner_id=user.id,
        provider_id=body.provider_id,
        encrypted_secret=encrypt_secret(body.api_key),
        label=body.label,
        meta_json=body.meta_json,
        is_active=True,
    )
    db.add(cred)
    await db.flush()

    # Immediately pull real catalog so Model Selector updates.
    try:
        await sync_provider_models(db, body.provider_id, api_key=body.api_key)
    except Exception as exc:  # noqa: BLE001
        # Credential is saved even if sync fails; client can retry sync.
        cred.meta_json = {**(cred.meta_json or {}), "last_sync_error": str(exc)[:500]}

    await db.refresh(cred)
    return cred


@router.get("/providers/credentials", response_model=list[CredentialOut])
async def list_credentials(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ProviderCredential).where(ProviderCredential.owner_id == user.id)
    )
    return result.scalars().all()


@router.get("/user-models", response_model=list[UserModelOut])
async def list_user_models(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Fast path: already have user_models.
    probe = await db.execute(
        select(UserModel.id).where(UserModel.owner_id == user.id).limit(1)
    )
    existing_id = probe.scalar_one_or_none()
    if existing_id:
        result = await db.execute(
            select(UserModel).where(
                UserModel.owner_id == user.id, UserModel.is_enabled.is_(True)
            )
        )
        return result.scalars().all()

    # Backward-compat fallback: if user_models were introduced but existing
    # installations still have only model_catalog_items + provider_credentials,
    # we can synthesize user_models on demand so UI works again.
    #
    # Note: if model_catalog_items were already dropped, there is nothing to sync.
    creds_res = await db.execute(
        select(ProviderCredential).where(
            ProviderCredential.owner_id == user.id,
            ProviderCredential.is_active.is_(True),
        )
    )
    creds = creds_res.scalars().all()
    if not creds:
        return []

    provider_ids = [c.provider_id for c in creds]
    creds_by_provider = {c.provider_id: c for c in creds}

    providers_res = await db.execute(
        select(ModelProvider).where(ModelProvider.id.in_(provider_ids))
    )
    providers = providers_res.scalars().all()
    by_provider_id = {p.id: p for p in providers}

    if not by_provider_id:
        return []

    items_res = await db.execute(
        select(ModelCatalogItem).where(ModelCatalogItem.provider_id.in_(provider_ids))
    )
    items = items_res.scalars().all()
    if not items:
        return []

    for item in items:
        provider = by_provider_id.get(item.provider_id)
        cred = creds_by_provider.get(item.provider_id)
        if not provider or not cred:
            continue

        db.add(
            UserModel(
                owner_id=user.id,
                provider_type=provider.type,
                provider_name=provider.name,
                base_url=provider.base_url,
                capabilities_json=item.capabilities_json or {},
                encrypted_api_key=cred.encrypted_secret,
                model_id=item.model_id,
                label=item.label,
                is_free=item.is_free,
                input_price=item.input_price,
                output_price=item.output_price,
                context_window=item.context_window,
                tags=item.tags or [],
                is_enabled=item.is_enabled,
            )
        )

    await db.flush()
    result = await db.execute(
        select(UserModel).where(
            UserModel.owner_id == user.id, UserModel.is_enabled.is_(True)
        )
    )
    return result.scalars().all()


@router.post("/user-models", response_model=UserModelOut)
async def create_user_model(
    body: UserModelCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    existing_q = await db.execute(
        select(UserModel).where(
            UserModel.owner_id == user.id,
            UserModel.provider_type == body.provider_type,
            UserModel.base_url == body.base_url,
            UserModel.model_id == body.model_id,
        )
    )
    existing = existing_q.scalar_one_or_none()
    if existing is None:
        existing = UserModel(owner_id=user.id, **body.model_dump(exclude={"api_key"}))
        existing.encrypted_api_key = encrypt_secret(body.api_key)
        db.add(existing)
    else:
        # Update connection and display fields for existing model connection.
        data = body.model_dump(exclude={"api_key"})
        for k, v in data.items():
            setattr(existing, k, v)
        existing.encrypted_api_key = encrypt_secret(body.api_key)
        existing.is_enabled = True

    await db.flush()
    await db.refresh(existing)
    return existing


@router.delete("/user-models/{user_model_id}", status_code=204)
async def delete_user_model(
    user_model_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Soft-delete: hide from lists; keep row so StepModelConfig FKs stay valid."""
    model = await db.get(UserModel, user_model_id)
    if model is None or model.owner_id != user.id:
        raise HTTPException(404, "User model not found")
    model.is_enabled = False
    await db.flush()
    return None


@router.patch("/user-models/{user_model_id}", response_model=UserModelOut)
async def update_user_model_key(
    user_model_id: UUID,
    body: UserModelKeyUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    model = await db.get(UserModel, user_model_id)
    if model is None or model.owner_id != user.id:
        raise HTTPException(404, "User model not found")
    key = (body.api_key or "").strip()
    if not key:
        raise HTTPException(400, "api_key is required")
    model.encrypted_api_key = encrypt_secret(key)
    model.is_enabled = True
    await db.flush()
    await db.refresh(model)
    return model


@router.post("/user-models/{user_model_id}/test", response_model=UserModelTestOut)
async def test_user_model(
    user_model_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    model = await db.get(UserModel, user_model_id)
    if model is None or model.owner_id != user.id:
        raise HTTPException(404, "User model not found")

    try:
        api_key = decrypt_secret(model.encrypted_api_key)
        if not api_key.strip():
            return {
                "ok": False,
                "provider": model.provider_name,
                "hint": "Ключ пустой. Добавьте модель заново с API-ключом.",
                "synced_models_count": None,
            }

        adapter = build_provider(
            model.provider_type, model.provider_name, model.base_url, model.capabilities_json
        )

        # Главная проверка — реальный chat/completions.
        # GET /models у Groq/OpenRouter часто даёт 403 даже при рабочем ключе.
        req = GenerateRequest(
            model=model.model_id,
            system="You are a helpful assistant.",
            user="Return the word OK.",
            temperature=0.0,
            max_tokens=5,
            response_json=False,
            timeout_seconds=30,
        )
        await adapter.generate(api_key, req)

        return {
            "ok": True,
            "provider": model.provider_name,
            "hint": "OK. Ключ рабочий и запрос к модели проходит.",
            "synced_models_count": None,
        }
    except ValueError as exc:
        return {
            "ok": False,
            "provider": model.provider_name,
            "hint": str(exc),
            "synced_models_count": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "provider": model.provider_name,
            "hint": str(exc),
            "synced_models_count": None,
        }


@router.post("/providers/test")
async def test_provider(
    body: ProviderTestRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    provider = await db.get(ModelProvider, body.provider_id)
    if provider is None:
        raise HTTPException(404, "Provider not found")
    key = body.api_key
    if not key:
        from app.services.generation import _resolve_api_key

        key = await _resolve_api_key(db, provider)
    adapter = build_provider(
        provider.type, provider.name, provider.base_url, provider.capabilities_json
    )
    ok = await adapter.validate_credentials(key) if key else False
    synced = 0
    if ok and key:
        try:
            items = await sync_provider_models(db, provider.id, api_key=key)
            synced = len(items)
        except Exception:  # noqa: BLE001
            synced = 0
    return {
        "ok": ok,
        "provider": provider.name,
        "synced_models": synced,
        "hint": (
            f"Ключ OK, загружено моделей: {synced}"
            if ok
            else "Ключ не принят или отсутствует. Без ключа модели этого провайдера не появятся в селекторе."
        ),
    }


@router.get("/providers/{provider_id}/models/sync", response_model=list[ModelOut])
async def sync_models(
    provider_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    raise HTTPException(
        410,
        "Model catalog endpoints are removed. Use /user-models to add your own BYOK-enabled models.",
    )
    try:
        items = await sync_provider_models(db, provider_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Не удалось обновить каталог: {exc}") from exc
    # Reload with provider relationship for names
    usable = await list_usable_models(db)
    by_id = {m.id: m for m in usable}
    out = []
    for item in items:
        m = by_id.get(item.id, item)
        out.append(_model_out(m) if getattr(m, "provider", None) else ModelOut.model_validate(item))
    return out


@router.get("/models", response_model=list[ModelOut])
async def list_models(
    free: bool | None = None,
    tag: str | None = None,
    usable_only: bool = True,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    raise HTTPException(
        410,
        "Model catalog endpoints are removed. Use /user-models to add your own BYOK-enabled models.",
    )
    if usable_only:
        models = await list_usable_models(db)
    else:
        result = await db.execute(
            select(ModelCatalogItem).where(ModelCatalogItem.is_enabled.is_(True))
        )
        models = list(result.scalars().all())
    if free is not None:
        models = [m for m in models if m.is_free is free]
    if tag:
        models = [m for m in models if tag in (m.tags or [])]
    return [_model_out(m) for m in models]


@router.get("/models/recommendations")
async def recommendations(
    step_type: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    raise HTTPException(
        410,
        "Model catalog endpoints are removed. Use /user-models instead.",
    )
    models = await list_usable_models(db)
    ranked = rank_models_for_step(step_type, models)
    meta = STEP_RECOMMENDATIONS.get(step_type, {})
    return {
        "step_type": step_type,
        "meta": meta,
        "usable_count": len(models),
        "models": [_model_out(m) for m in ranked[:40]],
        "empty_hint": (
            None
            if models
            else "Нет рабочих моделей. Добавьте API-ключ OpenRouter в разделе «Модели» и нажмите «Обновить модели»."
        ),
    }


def _is_placeholder_model_id(model_id: str) -> bool:
    # Keep aligned with app.services.catalog._is_placeholder_item
    mid = (model_id or "").lower()
    if "/" not in mid:
        return False
    if mid.endswith(("/free-demo", "/balanced", "/quality")):
        return True
    return any(k in mid for k in ("free-demo", "/balanced", "/quality", "demo", "balanced", "quality"))


@router.post("/providers/{provider_id}/models", response_model=ModelOut)
async def add_provider_model(
    provider_id: UUID,
    body: ModelAddIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    raise HTTPException(
        410,
        "Model catalog endpoints are removed. Add models via /user-models instead.",
    )
    provider = await db.get(ModelProvider, provider_id)
    if provider is None:
        raise HTTPException(404, "Provider not found")

    if not await provider_has_key(db, provider):
        raise HTTPException(
            400,
            "Нужен рабочий API-ключ для этого провайдера (BYOK), чтобы добавить модель вручную.",
        )

    existing_q = await db.execute(
        select(ModelCatalogItem).where(
            ModelCatalogItem.provider_id == provider.id,
            ModelCatalogItem.model_id == body.model_id,
        )
    )
    item = existing_q.scalar_one_or_none()
    if item is None:
        item = ModelCatalogItem(
            provider_id=provider.id,
            model_id=body.model_id,
            label=body.label,
            is_free=body.is_free,
            input_price=body.input_price,
            output_price=body.output_price,
            context_window=body.context_window,
            capabilities_json=body.capabilities_json,
            is_enabled=True,
            tags=body.tags,
        )
        db.add(item)
    else:
        item.label = body.label
        item.is_free = body.is_free
        item.input_price = body.input_price
        item.output_price = body.output_price
        item.context_window = body.context_window
        item.capabilities_json = body.capabilities_json
        item.is_enabled = True
        item.tags = body.tags
    await db.flush()
    await db.refresh(item)
    return _model_out(item)


@router.get("/providers/{provider_id}/models", response_model=list[ModelOut])
async def list_provider_models(
    provider_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    provider = await db.get(ModelProvider, provider_id)
    if provider is None:
        raise HTTPException(404, "Provider not found")
    if not await provider_has_key(db, provider):
        return []
    result = await db.execute(
        select(ModelCatalogItem).where(
            ModelCatalogItem.provider_id == provider_id,
            ModelCatalogItem.is_enabled.is_(True),
        )
    )
    items = [m for m in result.scalars().all() if not _is_placeholder_model_id(m.model_id)]
    return [_model_out(m) for m in items]


@router.post("/step-model-configs", response_model=StepModelConfigOut)
async def upsert_step_model_config(
    body: StepModelConfigIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = select(StepModelConfig).where(StepModelConfig.step_type == body.step_type)
    if body.project_id:
        q = q.where(StepModelConfig.project_id == body.project_id)
    else:
        q = q.where(StepModelConfig.project_id.is_(None))
    existing = (await db.execute(q)).scalar_one_or_none()
    if existing:
        for k, v in body.model_dump().items():
            setattr(existing, k, v)
        await db.flush()
        await db.refresh(existing)
        return existing
    cfg = StepModelConfig(**body.model_dump())
    db.add(cfg)
    await db.flush()
    await db.refresh(cfg)
    return cfg


@router.get("/step-model-configs", response_model=list[StepModelConfigOut])
async def list_step_configs(
    project_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = select(StepModelConfig)
    if project_id:
        q = q.where(StepModelConfig.project_id == project_id)
    return (await db.execute(q)).scalars().all()

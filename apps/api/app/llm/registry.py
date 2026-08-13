"""Provider registry and factory."""

from __future__ import annotations

from app.llm.openai_compatible import OpenAICompatibleProvider

# Built-in gateway presets — catalog is synced at runtime, not hardcoded.
PROVIDER_PRESETS: list[dict] = [
    {
        "name": "OpenRouter",
        "type": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "capabilities_json": {
            "structured_output": True,
            "vision": True,
            "free_models": True,
            "russian_friendly": False,
        },
    },
    {
        "name": "Hubris",
        "type": "hubris",
        "base_url": "https://api.hubris.ai/v1",
        "capabilities_json": {
            "structured_output": True,
            "vision": False,
            "free_models": True,
            "russian_friendly": False,
            "pricing_is_free_flag": True,
        },
    },
    {
        "name": "TsarRouter",
        "type": "tsarrouter",
        "base_url": "https://api.tsarrouter.ru/v1",
        "capabilities_json": {
            "structured_output": True,
            "vision": False,
            "free_models": False,
            "russian_friendly": True,
        },
    },
    {
        "name": "OpenAI Compatible",
        "type": "openai_compatible",
        "base_url": "https://api.openai.com/v1",
        "capabilities_json": {
            "structured_output": True,
            "vision": True,
            "free_models": False,
            "russian_friendly": False,
        },
    },
    {
        "name": "YandexGPT Compatible",
        "type": "yandex",
        "base_url": "https://llm.api.cloud.yandex.net/v1",
        "capabilities_json": {
            "structured_output": False,
            "vision": False,
            "free_models": False,
            "russian_friendly": True,
        },
    },
    {
        "name": "GigaChat Compatible",
        "type": "gigachat",
        "base_url": "https://gigachat.devices.sberbank.ru/api/v1",
        "capabilities_json": {
            "structured_output": False,
            "vision": False,
            "free_models": False,
            "russian_friendly": True,
        },
    },
]


def build_provider(provider_type: str, name: str, base_url: str, capabilities: dict | None = None):
    caps = capabilities or {}
    russian = bool(caps.get("russian_friendly"))
    structured = bool(caps.get("structured_output", True))
    vision = bool(caps.get("vision", False))
    return OpenAICompatibleProvider(
        name=name,
        base_url=base_url,
        supports_structured=structured,
        supports_vision=vision,
        russian_friendly=russian,
    )

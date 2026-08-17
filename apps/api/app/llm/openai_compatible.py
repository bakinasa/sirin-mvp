"""OpenAI-compatible chat completions adapter (OpenRouter, TsarRouter, Hubris, etc.)."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

import httpx

from app.llm.base import CostEstimate, GenerateRequest, GenerateResult, ModelInfo

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider:
    """
    Works with any OpenAI-compatible /v1 API.
    Used as the first concrete gateway for MVP.
    """

    def __init__(
        self,
        name: str,
        base_url: str,
        *,
        supports_structured: bool = True,
        supports_vision: bool = False,
        russian_friendly: bool = False,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self._supports_structured = supports_structured
        self._supports_vision = supports_vision
        self._russian_friendly = russian_friendly

    def _headers(self, api_key: str) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        # OpenRouter recommends these; harmless for other gateways.
        if "openrouter.ai" in self.base_url:
            headers["HTTP-Referer"] = "http://localhost:8080"
            headers["X-Title"] = "AI Studio 360"
        return headers

    async def list_models(self, api_key: str) -> list[ModelInfo]:
        url = f"{self.base_url}/models"
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(url, headers=self._headers(api_key))
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"{self.name} list_models failed {resp.status_code}: {resp.text[:300]}"
                )
            data = resp.json()
        items = data.get("data") or data.get("models") or []
        models: list[ModelInfo] = []
        for item in items:
            mid = item.get("id") or item.get("model") or ""
            if not mid:
                continue
            pricing = item.get("pricing") or {}
            is_free = _detect_free(mid, item, pricing)
            tags: list[str] = []
            if is_free:
                tags.append("free")
            else:
                tags.append("paid")
            if self._russian_friendly:
                tags.append("russian-friendly")
            if self._supports_structured:
                tags.append("structured-output")
            if ":free" in mid or mid.endswith("/free") or mid == "openrouter/free":
                tags.append("recommended")
            ctx = item.get("context_length") or item.get("context_window")
            if ctx and int(ctx) >= 100_000:
                tags.append("long-context")
            architecture = item.get("architecture") or {}
            modality = str(architecture.get("modality") or item.get("modality") or "")
            if "image" in modality or self._supports_vision:
                tags.append("vision")
            models.append(
                ModelInfo(
                    model_id=mid,
                    label=item.get("name") or mid,
                    is_free=is_free,
                    input_price=_price(pricing.get("prompt") or pricing.get("input")),
                    output_price=_price(pricing.get("completion") or pricing.get("output")),
                    context_window=int(ctx) if ctx else None,
                    capabilities={
                        "structured_output": self._supports_structured,
                        "vision": "vision" in tags,
                    },
                    tags=tags,
                )
            )
        return models

    async def validate_credentials(self, api_key: str) -> bool:
        if not api_key:
            return False
        url = f"{self.base_url}/models"
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, headers=self._headers(api_key))
            # 401 = ключ точно отвергнут.
            # 403 на /models часто бывает у Groq/OpenRouter при рабочем chat — не считаем фатальным.
            if resp.status_code == 401:
                return False
            if resp.status_code == 403:
                return True
            return resp.status_code < 500

    async def generate(self, api_key: str, request: GenerateRequest) -> GenerateResult:
        url = f"{self.base_url}/chat/completions"
        body: dict[str, Any] = {
            "model": request.model,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
        }
        if request.response_json and self._supports_structured:
            body["response_format"] = {"type": "json_object"}

        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=float(request.timeout_seconds)) as client:
            resp = await client.post(url, headers=self._headers(api_key), json=body)
            latency = int((time.perf_counter() - started) * 1000)
            if resp.status_code >= 400:
                raise RuntimeError(f"{self.name} error {resp.status_code}: {resp.text[:500]}")
            data = resp.json()

        choices = data.get("choices") or (data.get("data") or {}).get("choices") or []
        choice = choices[0] if choices else {}
        message = choice.get("message") or choice.get("delta") or {}
        content = _prefer_jsonish(
            _coerce_message_content(message),
            _coerce_content_value(choice.get("text")),
            _coerce_content_value(choice.get("content")),
        )
        usage = data.get("usage") or {}
        if not content.strip():
            logger.warning(
                "Empty LLM content model=%s finish=%s tokens_in=%s tokens_out=%s message_keys=%s",
                request.model,
                choice.get("finish_reason") or choice.get("native_finish_reason"),
                usage.get("prompt_tokens"),
                usage.get("completion_tokens"),
                list(message.keys()) if isinstance(message, dict) else type(message).__name__,
            )
        return GenerateResult(
            content=content,
            raw=data,
            token_input=int(usage.get("prompt_tokens") or 0),
            token_output=int(usage.get("completion_tokens") or 0),
            latency_ms=latency,
            model=request.model,
        )

    def estimate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        input_price: Optional[float],
        output_price: Optional[float],
    ) -> CostEstimate:
        return CostEstimate(input_tokens, output_tokens, input_price, output_price)

    def supports_structured_output(self) -> bool:
        return self._supports_structured

    def supports_vision(self) -> bool:
        return self._supports_vision

    def supports_fallback(self) -> bool:
        return True


def _coerce_message_content(message: dict[str, Any]) -> str:
    """Read assistant text from OpenAI, DeepSeek and multipart payloads."""
    if not isinstance(message, dict):
        return _coerce_content_value(message)
    texts = [
        _coerce_content_value(message.get(key))
        for key in (
            "content",
            "reasoning_content",
            "reasoning",
            "text",
            "output_text",
            "reasoning_details",
        )
    ]
    return _prefer_jsonish(*texts)


def _prefer_jsonish(*texts: str) -> str:
    candidates = [text.strip() for text in texts if text and str(text).strip()]
    for text in candidates:
        if "brief_points" in text or text.startswith("{") or text.startswith("```"):
            return text
    return candidates[0] if candidates else ""


def _coerce_content_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(
                    _coerce_content_value(
                        item.get("text")
                        or item.get("content")
                        or item.get("reasoning")
                        or item.get("output_text")
                        or item.get("summary")
                    )
                )
        return "".join(parts)
    if isinstance(value, dict):
        if any(key in value for key in ("brief_points", "sections", "short")):
            return json.dumps(value, ensure_ascii=False)
        for key in ("text", "content", "reasoning", "output_text", "summary"):
            inner = value.get(key)
            if inner:
                text = _coerce_content_value(inner)
                if text.strip():
                    return text
        for key in ("parts", "reasoning_details"):
            inner = value.get(key)
            if inner:
                text = _coerce_content_value(inner)
                if text.strip():
                    return text
        return ""
    return str(value)


def _price(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _detect_free(model_id: str, item: dict[str, Any], pricing: dict[str, Any]) -> bool:
    if ":free" in model_id or model_id.endswith("/free") or model_id == "openrouter/free":
        return True
    if item.get("is_free") or pricing.get("is_free"):
        return True
    prompt = _price(pricing.get("prompt") if "prompt" in pricing else pricing.get("input"))
    completion = _price(
        pricing.get("completion") if "completion" in pricing else pricing.get("output")
    )
    if prompt is not None and completion is not None and prompt == 0 and completion == 0:
        return True
    return False

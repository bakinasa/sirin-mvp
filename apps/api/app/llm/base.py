"""LLM provider protocol and shared DTOs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol


@dataclass
class ModelInfo:
    model_id: str
    label: str
    is_free: bool = False
    input_price: Optional[float] = None
    output_price: Optional[float] = None
    context_window: Optional[int] = None
    capabilities: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)


@dataclass
class GenerateRequest:
    model: str
    system: str
    user: str
    temperature: float = 0.2
    max_tokens: int = 4096
    response_json: bool = True
    timeout_seconds: int = 120
    extra_body: dict[str, Any] = field(default_factory=dict)
    assistant_prefill: str = ""


@dataclass
class GenerateResult:
    content: str
    raw: dict[str, Any]
    token_input: int = 0
    token_output: int = 0
    latency_ms: int = 0
    model: str = ""


@dataclass
class CostEstimate:
    input_tokens: int
    output_tokens: int
    input_price_per_m: Optional[float]
    output_price_per_m: Optional[float]

    @property
    def total(self) -> Optional[float]:
        if self.input_price_per_m is None or self.output_price_per_m is None:
            return None
        return (
            self.input_tokens / 1_000_000 * self.input_price_per_m
            + self.output_tokens / 1_000_000 * self.output_price_per_m
        )


class LLMProvider(Protocol):
    """Unified interface for all LLM gateways."""

    name: str

    async def list_models(self, api_key: str) -> list[ModelInfo]: ...

    async def validate_credentials(self, api_key: str) -> bool: ...

    async def generate(self, api_key: str, request: GenerateRequest) -> GenerateResult: ...

    def estimate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        input_price: Optional[float],
        output_price: Optional[float],
    ) -> CostEstimate: ...

    def supports_structured_output(self) -> bool: ...

    def supports_vision(self) -> bool: ...

    def supports_fallback(self) -> bool: ...

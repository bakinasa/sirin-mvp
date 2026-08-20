"""Dynamic token/char budgets from model context window (no artificial 8192/14k caps)."""

from __future__ import annotations

from typing import Any

CHARS_PER_TOKEN = 2.4
GROQ_REQUEST_TOKEN_BUDGET = 11000
RESERVE_TOKENS = 512
MIN_OUTPUT_TOKENS = 2048
# Soft ceiling for long JSON docs (scenario with 4–10 scenes). Uncapped
# context_window − prompt can be 100k+ and makes providers hang / 504.
PIPELINE_OUTPUT_CAP = 16384

# Context blocks passed to the LLM in full — never truncated in render_context_as_text.
FULL_CONTEXT_BLOCK_IDS = frozenset(
    {
        "project_metadata",
        "brief",
        "profession_map",
        "expert_qa",
        "current_outline",
        "target_block",
        "document_structure",
        "document_outline",
        "conversation_state",
    }
)


def estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / CHARS_PER_TOKEN))


def is_tight_token_limit(model: Any) -> bool:
    name = f"{getattr(model, 'provider_name', '')} {getattr(model, 'base_url', '')}".lower()
    return "groq" in name


def request_token_budget(model: Any) -> int:
    if is_tight_token_limit(model):
        return GROQ_REQUEST_TOKEN_BUDGET
    ctx = getattr(model, "context_window", None) or 128000
    return max(8000, int(ctx))


def compute_max_tokens(model: Any, system: str, user: str, *, cap: int | None = None) -> int:
    """Output budget = remaining context after prompt, with a soft pipeline ceiling.

    We no longer hard-cap at 8192, but we also must not request 50k–100k completion
    tokens — gateways then run for minutes and nginx returns Gateway Time-out.
    """
    input_tokens = estimate_tokens(system) + estimate_tokens(user)
    if is_tight_token_limit(model):
        remaining = GROQ_REQUEST_TOKEN_BUDGET - input_tokens - 256
        result = max(1024, min(4096, remaining))
    else:
        ctx = request_token_budget(model)
        remaining = ctx - input_tokens - RESERVE_TOKENS
        result = max(MIN_OUTPUT_TOKENS, remaining)
        # Default soft ceiling when caller does not pass a tighter cap.
        if cap is None:
            result = min(PIPELINE_OUTPUT_CAP, result)
    if cap is not None:
        return min(cap, result)
    return result


def should_truncate_block(block_id: str) -> bool:
    return block_id not in FULL_CONTEXT_BLOCK_IDS

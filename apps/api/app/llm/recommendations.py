"""Task-based model recommendation heuristics."""

from __future__ import annotations

from app.domain.enums import StepType

# Maps pipeline step → preferred capability tags for UI recommendations.
STEP_RECOMMENDATIONS: dict[str, dict] = {
    StepType.BRIEF: {
        "label": "Summarization / extraction",
        "prefer_tags": ["free", "cheap"],
        "prefer_strength": "light",
    },
    StepType.PROFESSION_MAP: {
        "label": "Profession map",
        "prefer_tags": ["balanced", "structured-output"],
        "prefer_strength": "balanced",
    },
    StepType.SCENARIO_PLAN: {
        "label": "Scenario + shooting plan",
        "prefer_tags": ["structured-output", "balanced"],
        "prefer_strength": "balanced",
    },
    StepType.DRAFT_TZ: {
        "label": "Draft TZ",
        "prefer_tags": ["balanced", "structured-output"],
        "prefer_strength": "balanced",
    },
    StepType.EXPERT_SYNTHESIS: {
        "label": "Expert synthesis",
        "prefer_tags": ["reasoning", "paid"],
        "prefer_strength": "strong",
    },
    StepType.FINAL_TZ: {
        "label": "Final polishing",
        "prefer_tags": ["paid", "quality"],
        "prefer_strength": "strong",
    },
    StepType.SCENE_BREAKDOWN: {
        "label": "Scene breakdown",
        "prefer_tags": ["structured-output", "balanced"],
        "prefer_strength": "balanced",
    },
    StepType.PRODUCTION_PLANNING: {
        "label": "Production planning",
        "prefer_tags": ["balanced", "structured-output"],
        "prefer_strength": "balanced",
    },
    StepType.STORYBOARD: {
        "label": "Storyboard",
        "prefer_tags": ["structured-output", "vision"],
        "prefer_strength": "balanced",
    },
}


def rank_models_for_step(step_type: str, models: list) -> list:
    """Sort catalog models putting recommended ones first."""
    meta = STEP_RECOMMENDATIONS.get(step_type, {})
    prefer = set(meta.get("prefer_tags") or [])
    strength = meta.get("prefer_strength", "balanced")

    def score(m) -> tuple:
        tags = set(m.tags or [])
        caps = m.capabilities_json or {}
        s = 0
        s += len(tags & prefer) * 10
        if "structured-output" in prefer and caps.get("structured_output"):
            s += 5
        if m.is_free:
            s += 12  # prefer free when available
        if "recommended" in tags:
            s += 8
        if strength == "strong" and not m.is_free:
            s += 4
        mid = (m.model_id or "").lower()
        if "openrouter/free" in mid or mid.endswith(":free"):
            s += 15
        if "russian-friendly" in tags:
            s += 2
        provider_name = ""
        if getattr(m, "provider", None) is not None:
            provider_name = m.provider.name or ""
        return (-s, provider_name, m.label)

    return sorted(models, key=score)

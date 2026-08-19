"""Domain enums shared across API and worker."""

from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class ProjectStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class StepStatus(StrEnum):
    """Human-in-the-loop statuses for every pipeline step."""

    DRAFT = "draft"
    AI_GENERATED = "ai_generated"
    UNDER_REVIEW = "under_review"
    NEEDS_REVISION = "needs_revision"
    APPROVED = "approved"
    LOCKED = "locked"
    OUTDATED = "outdated"


class StepType(StrEnum):
    BRIEF = "brief"
    PROFESSION_MAP = "profession_map"
    SCENARIO_PLAN = "scenario_plan"
    EXPORT = "export"
    # Legacy steps kept for existing DB rows; hidden from the v2 UX.
    DRAFT_TZ = "draft_tz"
    EXPERT_FEEDBACK = "expert_feedback"
    EXPERT_SYNTHESIS = "expert_synthesis"
    FINAL_TZ = "final_tz"
    SCENE_BREAKDOWN = "scene_breakdown"
    PRODUCTION_PLANNING = "production_planning"
    STORYBOARD = "storyboard"


# User-facing HITL pipeline.
PIPELINE_ORDER: list[StepType] = [
    StepType.BRIEF,
    StepType.PROFESSION_MAP,
    StepType.SCENARIO_PLAN,
    StepType.EXPORT,
]

VISIBLE_STEP_TYPES: set[str] = {s.value for s in PIPELINE_ORDER}


def later_pipeline_steps(step_type: str) -> list[str]:
    """Step types after `step_type` in the user-facing pipeline."""
    values = [s.value for s in PIPELINE_ORDER]
    try:
        idx = values.index(step_type)
    except ValueError:
        return []
    return values[idx + 1 :]


def previous_step_allows_generate(prev_type: str, has_artifact: bool) -> bool:
    """Brief is filled manually; later steps only need a current artifact."""
    if prev_type == StepType.BRIEF.value:
        return True
    return has_artifact

LEGACY_STEP_TYPES: set[str] = {
    StepType.DRAFT_TZ.value,
    StepType.EXPERT_FEEDBACK.value,
    StepType.EXPERT_SYNTHESIS.value,
    StepType.FINAL_TZ.value,
    StepType.SCENE_BREAKDOWN.value,
    StepType.PRODUCTION_PLANNING.value,
    StepType.STORYBOARD.value,
}


class ArtifactStatus(StrEnum):
    DRAFT = "draft"
    AI_GENERATED = "ai_generated"
    EDITED = "edited"
    APPROVED = "approved"
    REJECTED = "rejected"


class ArtifactFormat(StrEnum):
    MARKDOWN = "markdown"
    JSON = "json"
    TEXT = "text"


class ChangeType(StrEnum):
    MANUAL = "manual"
    AI_GENERATE = "ai_generate"
    AI_PATCH = "ai_patch"
    RESTORE = "restore"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExpertStatus(StrEnum):
    INVITED = "invited"
    PENDING = "pending"
    RECEIVED = "received"
    DONE = "done"


class ExportType(StrEnum):
    MARKDOWN = "markdown"
    JSON = "json"
    TEXT_BUNDLE = "text_bundle"
    DOCX_SCENARIO = "docx_scenario"


class ExportStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"


class ProviderType(StrEnum):
    OPENAI_COMPATIBLE = "openai_compatible"
    OPENROUTER = "openrouter"
    HUBRIS = "hubris"
    TSARROUTER = "tsarrouter"
    YANDEX = "yandex"
    GIGACHAT = "gigachat"


class ChatMode(StrEnum):
    ASK = "ask"
    LOCAL_EDIT = "local_edit"
    GLOBAL_EDIT = "global_edit"


class PatchScope(StrEnum):
    LOCAL = "local"
    GLOBAL = "global"


class PatchStatus(StrEnum):
    DRAFT = "draft"
    APPLIED = "applied"
    DISCARDED = "discarded"


class ParseStatus(StrEnum):
    PENDING = "pending"
    PARSING = "parsing"
    SUMMARIZING = "summarizing"
    READY = "ready"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"


class SourceType(StrEnum):
    SOP = "sop"
    INSTRUCTION = "instruction"
    REGULATION = "regulation"
    NOTE = "note"
    CHECKLIST = "checklist"
    INTERVIEW_NOTE = "interview_note"
    OTHER = "other"


class ItemStatus(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EDITED = "edited"


class CommentStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"

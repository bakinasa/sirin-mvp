"""Pydantic request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: UUID
    name: str
    email: EmailStr
    role: str

    model_config = {"from_attributes": True}


class ProjectCreate(BaseModel):
    title: str
    client_name: str = ""
    profession: str = ""
    audience: str = ""
    delivery_format: str = ""
    expected_duration: str = ""
    constraints: str = ""
    source_materials: str = ""


class ProjectUpdate(BaseModel):
    title: Optional[str] = None
    client_name: Optional[str] = None
    profession: Optional[str] = None
    audience: Optional[str] = None
    delivery_format: Optional[str] = None
    expected_duration: Optional[str] = None
    constraints: Optional[str] = None
    source_materials: Optional[str] = None
    status: Optional[str] = None


class ProjectOut(BaseModel):
    id: UUID
    title: str
    client_name: str
    profession: str
    audience: str
    delivery_format: str
    expected_duration: str
    constraints: str
    source_materials: str
    status: str
    owner_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BriefOut(BaseModel):
    id: UUID
    project_id: UUID
    content_json: dict[str, Any]
    version: int
    status: str
    updated_at: datetime

    model_config = {"from_attributes": True}


class BriefUpdate(BaseModel):
    content_json: dict[str, Any]
    status: Optional[str] = None


class ExpertCreate(BaseModel):
    name: str
    role: str = ""
    contact: str = ""
    status: str = "invited"


class ExpertOut(BaseModel):
    id: UUID
    project_id: UUID
    name: str
    role: str
    contact: str
    status: str

    model_config = {"from_attributes": True}


class ExpertFeedbackCreate(BaseModel):
    expert_id: UUID
    content: str
    structured_tags: list[Any] = Field(default_factory=list)
    attachments: list[Any] = Field(default_factory=list)


class ExpertFeedbackOut(BaseModel):
    id: UUID
    expert_id: UUID
    project_id: UUID
    content: str
    structured_tags: list[Any]
    attachments: list[Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class PipelineStepOut(BaseModel):
    id: UUID
    project_id: UUID
    step_type: str
    order_index: int
    status: str
    current_artifact_id: Optional[UUID]
    approved_artifact_id: Optional[UUID]

    model_config = {"from_attributes": True}


class PipelineRunRequest(BaseModel):
    step_type: str
    operator_prompt: Optional[str] = None
    primary_model_id: Optional[UUID] = None
    fallback_model_id: Optional[UUID] = None


class PipelineRunOut(BaseModel):
    id: UUID
    project_id: UUID
    pipeline_step_id: UUID
    status: str
    provider_name: str
    model_name: str
    prompt_template_version: str
    operator_prompt_text: str
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    latency_ms: Optional[int]
    token_input: Optional[int]
    token_output: Optional[int]
    estimated_cost: Optional[float]
    error_message: str
    fallback_used: bool

    model_config = {"from_attributes": True}


class ArtifactOut(BaseModel):
    id: UUID
    project_id: UUID
    step_type: str
    source_run_id: Optional[UUID]
    parent_artifact_id: Optional[UUID]
    content: Any
    format: str
    version: int
    status: str
    approved_by: Optional[UUID]
    approved_at: Optional[datetime]
    change_type: str = "ai_generate"
    change_summary: str = ""
    frozen: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ArtifactUpdate(BaseModel):
    content: Any
    comment: str = ""


class ArtifactAction(BaseModel):
    comment: str = ""


class PromptTemplateOut(BaseModel):
    id: UUID
    step_type: str
    role_name: str
    version: str
    content: str
    is_active: bool

    model_config = {"from_attributes": True}


class PromptTemplateCreate(BaseModel):
    step_type: str
    role_name: str
    version: str
    content: str
    is_active: bool = True


class PromptTemplateUpdate(BaseModel):
    role_name: Optional[str] = None
    content: Optional[str] = None
    is_active: Optional[bool] = None


class OperatorPresetOut(BaseModel):
    id: UUID
    step_type: str
    title: str
    content: str
    is_default: bool

    model_config = {"from_attributes": True}


class OperatorPresetCreate(BaseModel):
    step_type: str
    title: str
    content: str
    is_default: bool = False


class ProviderOut(BaseModel):
    id: UUID
    name: str
    type: str
    base_url: str
    capabilities_json: dict[str, Any]
    is_active: bool

    model_config = {"from_attributes": True}


class ProviderCreate(BaseModel):
    name: str
    type: str
    base_url: str
    capabilities_json: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class CredentialCreate(BaseModel):
    provider_id: UUID
    api_key: str
    label: str = "BYOK"
    meta_json: dict[str, Any] = Field(default_factory=dict)


class CredentialOut(BaseModel):
    id: UUID
    provider_id: UUID
    owner_id: UUID
    label: str
    meta_json: dict[str, Any]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ProviderTestRequest(BaseModel):
    provider_id: UUID
    api_key: Optional[str] = None
    model_id: Optional[str] = None


class ModelOut(BaseModel):
    id: UUID
    provider_id: UUID
    model_id: str
    label: str
    is_free: bool
    input_price: Optional[float]
    output_price: Optional[float]
    context_window: Optional[int]
    capabilities_json: dict[str, Any]
    is_enabled: bool
    tags: list[Any]
    provider_name: Optional[str] = None

    model_config = {"from_attributes": True}


class ModelAddIn(BaseModel):
    """
    Manual model entry for BYOK providers.

    This is used when a desired model is not returned by catalog sync.
    """

    model_id: str
    label: str
    is_free: bool = False
    input_price: Optional[float] = None
    output_price: Optional[float] = None
    context_window: Optional[int] = None
    capabilities_json: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class UserModelCreate(BaseModel):
    """
    User-owned LLM model connection.

    We store provider connection details + BYOK for the exact model_id so the
    frontend can fully control what gets sent to the upstream API.
    """

    label: str

    # Where to send requests.
    provider_type: str
    provider_name: str
    base_url: str

    # Upstream model to call (e.g. "gpt-4o-mini" or vendor-specific id).
    model_id: str

    # Connection flags/capabilities used by the adapter (e.g. structured output).
    capabilities_json: dict[str, Any] = Field(default_factory=dict)

    # Upstream API key (BYOK). Encrypted at rest on the backend.
    api_key: str

    # Optional pricing metadata for cost estimate (can be empty).
    is_free: bool = False
    input_price: Optional[float] = None
    output_price: Optional[float] = None
    context_window: Optional[int] = None

    # Optional tags for future UX filtering.
    tags: list[str] = Field(default_factory=list)


class UserModelOut(BaseModel):
    id: UUID
    owner_id: UUID

    label: str
    provider_type: str
    provider_name: str
    base_url: str
    capabilities_json: dict[str, Any]

    model_id: str
    is_free: bool
    input_price: Optional[float]
    output_price: Optional[float]
    context_window: Optional[int]
    tags: list[Any]
    is_enabled: bool

    model_config = {"from_attributes": True}


class UserModelTestOut(BaseModel):
    ok: bool
    provider: str
    hint: str
    synced_models_count: Optional[int] = None


class ProviderAddModelResponse(BaseModel):
    model: ModelOut

    model_config = {"from_attributes": True}


class StepModelConfigIn(BaseModel):
    project_id: Optional[UUID] = None
    step_type: str
    primary_model_id: Optional[UUID] = None
    fallback_model_id: Optional[UUID] = None
    temperature: float = 0.2
    max_tokens: int = 4096
    reasoning_effort: str = "medium"
    budget_limit: Optional[float] = None
    max_retries: int = 2
    timeout_seconds: int = 120


class StepModelConfigOut(StepModelConfigIn):
    id: UUID

    model_config = {"from_attributes": True}


class ExportCreate(BaseModel):
    export_type: str = "markdown"


class ExportOut(BaseModel):
    id: UUID
    project_id: UUID
    export_type: str
    status: str
    result_path: str
    result_content: Optional[Any]
    error_message: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ContextBundleOut(BaseModel):
    step_type: str
    blocks: list[dict[str, Any]]
    prompt_template_version: str
    system_prompt: str
    operator_prompt: str
    context_text: str = ""
    user_message: str = ""


class ProjectMetricsOut(BaseModel):
    project_id: UUID
    total_runs: int
    regenerations: int
    manual_edits: int
    total_cost: float
    avg_latency_ms: float
    approved_without_heavy_edit: int


class SourceOut(BaseModel):
    id: UUID
    project_id: UUID
    title: str
    source_type: str
    file_path: str
    mime_type: str
    parse_status: str
    parse_error: str
    summary_short_json: Any
    summary_structured_json: Any
    important_chunks_json: Any
    created_at: datetime
    updated_at: datetime
    has_parsed_text: bool = False

    model_config = {"from_attributes": True}


class SourceDetailOut(SourceOut):
    parsed_text: str = ""
    chunks: list[dict[str, Any]] = Field(default_factory=list)


class SourceReprocessIn(BaseModel):
    primary_model_id: Optional[UUID] = None
    fallback_model_id: Optional[UUID] = None


class ChatRequest(BaseModel):
    mode: str = "ask"
    body: str
    target_id: Optional[str] = None
    primary_model_id: Optional[UUID] = None
    fallback_model_id: Optional[UUID] = None


class ChatMessageOut(BaseModel):
    id: UUID
    session_id: UUID
    role: str
    body: str
    applied_patch_id: Optional[UUID] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatSessionOut(BaseModel):
    id: UUID
    project_id: UUID
    stage_type: str
    mode: str
    summary_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    messages: list[ChatMessageOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ChatResponse(BaseModel):
    session: ChatSessionOut
    message: ChatMessageOut
    patch: Optional["PatchOut"] = None


class PatchOut(BaseModel):
    id: UUID
    project_id: UUID
    stage_type: str
    artifact_id: Optional[UUID]
    scope: str
    target_id: str
    instruction: str
    patch_json: Any
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class CommentCreate(BaseModel):
    stage_type: str
    target_type: str = "block"
    target_id: str = ""
    body: str
    artifact_id: Optional[UUID] = None


class CommentMessageOut(BaseModel):
    id: UUID
    thread_id: UUID
    body: str
    message_type: str
    decision: str
    created_by: Optional[UUID]
    created_at: datetime

    model_config = {"from_attributes": True}


class CommentThreadOut(BaseModel):
    id: UUID
    project_id: UUID
    stage_type: str
    artifact_id: Optional[UUID]
    target_type: str
    target_id: str
    status: str
    created_by: Optional[UUID]
    created_at: datetime
    messages: list[CommentMessageOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ItemPatchIn(BaseModel):
    content: dict[str, Any]


class GenerateStageIn(BaseModel):
    operator_prompt: Optional[str] = None
    primary_model_id: Optional[UUID] = None
    fallback_model_id: Optional[UUID] = None


class SaveVersionIn(BaseModel):
    change_summary: str = ""


ChatResponse.model_rebuild()

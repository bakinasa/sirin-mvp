"""ORM models for AI Studio 360."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="operator")


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    client_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    profession: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    audience: Mapped[str] = mapped_column(Text, nullable=False, default="")
    delivery_format: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    expected_duration: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    constraints: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_materials: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))

    owner: Mapped[User] = relationship("User")
    brief: Mapped[Optional[Brief]] = relationship("Brief", back_populates="project", uselist=False)
    steps: Mapped[list[PipelineStep]] = relationship("PipelineStep", back_populates="project")
    experts: Mapped[list[Expert]] = relationship("Expert", back_populates="project")
    sources: Mapped[list[ProjectSource]] = relationship("ProjectSource", back_populates="project")


class Brief(Base, TimestampMixin):
    __tablename__ = "briefs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), unique=True
    )
    content_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft")

    project: Mapped[Project] = relationship("Project", back_populates="brief")


class Expert(Base, TimestampMixin):
    __tablename__ = "experts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    contact: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="invited")

    project: Mapped[Project] = relationship("Project", back_populates="experts")
    feedback: Mapped[list[ExpertFeedback]] = relationship("ExpertFeedback", back_populates="expert")


class ExpertFeedback(Base, TimestampMixin):
    __tablename__ = "expert_feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    expert_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("experts.id"))
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"))
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    structured_tags: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    attachments: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)

    expert: Mapped[Expert] = relationship("Expert", back_populates="feedback")


class PipelineStep(Base, TimestampMixin):
    __tablename__ = "pipeline_steps"
    __table_args__ = (UniqueConstraint("project_id", "step_type", name="uq_project_step"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"))
    step_type: Mapped[str] = mapped_column(String(80), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft")
    current_artifact_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("artifacts.id", use_alter=True), nullable=True
    )
    approved_artifact_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("artifacts.id", use_alter=True), nullable=True
    )

    project: Mapped[Project] = relationship("Project", back_populates="steps")


class Artifact(Base, TimestampMixin):
    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"))
    step_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pipeline_runs.id", use_alter=True), nullable=True
    )
    parent_artifact_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("artifacts.id"), nullable=True
    )
    content: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    format: Mapped[str] = mapped_column(String(50), nullable=False, default="json")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft")
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    change_type: Mapped[str] = mapped_column(String(50), nullable=False, default="ai_generate")
    change_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    frozen: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    edits: Mapped[list[HumanEdit]] = relationship("HumanEdit", back_populates="artifact")


class HumanEdit(Base):
    __tablename__ = "human_edits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    artifact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("artifacts.id"))
    editor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    diff: Mapped[str] = mapped_column(Text, nullable=False, default="")
    before_content: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    after_content: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    artifact: Mapped[Artifact] = relationship("Artifact", back_populates="edits")


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"))
    pipeline_step_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pipeline_steps.id")
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="queued")
    provider_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    model_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    prompt_template_version: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    operator_prompt_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    context_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    token_input: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    token_output: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    estimated_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    fallback_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UserModel(Base, TimestampMixin):
    """
    User-owned model configuration used for actual LLM calls.

    This replaces the old "catalog sync" approach: instead of relying on
    ModelCatalogItem (synced via provider API), we store exactly what is
    needed to connect to the provider (BYOK + base_url + capabilities) and
    which model_id should be called.
    """

    __tablename__ = "user_models"
    __table_args__ = (
        # Keep duplicates out for the same user.
        UniqueConstraint("owner_id", "provider_type", "base_url", "model_id", name="uq_user_provider_model"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))

    # Provider connection details (what adapter should be built with).
    provider_type: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(255), nullable=False, default="Custom")
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    capabilities_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    # Encrypted BYOK (per this user model connection).
    encrypted_api_key: Mapped[str] = mapped_column(Text, nullable=False)

    # Model-specific fields.
    model_id: Mapped[str] = mapped_column(String(255), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    is_free: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    input_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    output_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    context_window: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Optional tags for UX filtering/search in future.
    tags: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)

    # (Optional) soft enable/disable; we will default to enabled.
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class PromptTemplate(Base, TimestampMixin):
    __tablename__ = "prompt_templates"
    __table_args__ = (UniqueConstraint("step_type", "version", name="uq_prompt_step_version"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    step_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    role_name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class OperatorPromptPreset(Base, TimestampMixin):
    __tablename__ = "operator_prompt_presets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    step_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class PromptEditHistory(Base):
    """History of operator prompt edits before AI runs."""

    __tablename__ = "prompt_edit_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"))
    step_type: Mapped[str] = mapped_column(String(80), nullable=False)
    editor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ModelProvider(Base, TimestampMixin):
    __tablename__ = "model_providers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    type: Mapped[str] = mapped_column(String(80), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    capabilities_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    credentials: Mapped[list[ProviderCredential]] = relationship(
        "ProviderCredential", back_populates="provider"
    )
    models: Mapped[list[ModelCatalogItem]] = relationship(
        "ModelCatalogItem", back_populates="provider"
    )


class ProviderCredential(Base, TimestampMixin):
    __tablename__ = "provider_credentials"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_providers.id")
    )
    encrypted_secret: Mapped[str] = mapped_column(Text, nullable=False)
    meta_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False, default="BYOK")

    provider: Mapped[ModelProvider] = relationship("ModelProvider", back_populates="credentials")


class ModelCatalogItem(Base, TimestampMixin):
    __tablename__ = "model_catalog_items"
    __table_args__ = (
        UniqueConstraint("provider_id", "model_id", name="uq_provider_model"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_providers.id")
    )
    model_id: Mapped[str] = mapped_column(String(255), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    is_free: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    input_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    output_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    context_window: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    capabilities_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    tags: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)

    provider: Mapped[ModelProvider] = relationship("ModelProvider", back_populates="models")


class StepModelConfig(Base, TimestampMixin):
    __tablename__ = "step_model_configs"
    __table_args__ = (
        UniqueConstraint("project_id", "step_type", name="uq_project_step_model"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True
    )
    step_type: Mapped[str] = mapped_column(String(80), nullable=False)
    primary_model_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_models.id"), nullable=True
    )
    fallback_model_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_models.id"), nullable=True
    )
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.2)
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=4096)
    reasoning_effort: Mapped[str] = mapped_column(String(50), nullable=False, default="medium")
    budget_limit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=120)


class ExportJob(Base, TimestampMixin):
    __tablename__ = "export_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"))
    export_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    result_path: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    result_content: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")


class ProjectSource(Base, TimestampMixin):
    __tablename__ = "project_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"))
    title: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    source_type: Mapped[str] = mapped_column(String(80), nullable=False, default="other")
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    parsed_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    parse_status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    parse_error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary_short_json: Mapped[Any] = mapped_column(JSONB, nullable=False, default=list)
    summary_structured_json: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    important_chunks_json: Mapped[Any] = mapped_column(JSONB, nullable=False, default=list)
    summary_job_json: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    project: Mapped[Project] = relationship("Project", back_populates="sources")
    chunks: Mapped[list[ProjectSourceChunk]] = relationship(
        "ProjectSourceChunk", back_populates="source", cascade="all, delete-orphan"
    )


class ProjectSourceChunk(Base):
    __tablename__ = "project_source_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project_sources.id", ondelete="CASCADE")
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    page_ref: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    source: Mapped[ProjectSource] = relationship("ProjectSource", back_populates="chunks")


class StageChatSession(Base, TimestampMixin):
    __tablename__ = "stage_chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"))
    stage_type: Mapped[str] = mapped_column(String(80), nullable=False)
    mode: Mapped[str] = mapped_column(String(50), nullable=False, default="ask")
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    messages: Mapped[list[StageChatMessage]] = relationship(
        "StageChatMessage", back_populates="session", cascade="all, delete-orphan"
    )


class StageChatMessage(Base):
    __tablename__ = "stage_chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stage_chat_sessions.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    applied_patch_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("artifact_patches.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped[StageChatSession] = relationship("StageChatSession", back_populates="messages")


class ArtifactPatch(Base):
    __tablename__ = "artifact_patches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"))
    stage_type: Mapped[str] = mapped_column(String(80), nullable=False)
    artifact_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("artifacts.id"), nullable=True
    )
    artifact_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("artifacts.id"), nullable=True
    )
    scope: Mapped[str] = mapped_column(String(50), nullable=False, default="local")
    target_id: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    instruction: Mapped[str] = mapped_column(Text, nullable=False, default="")
    patch_json: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft")
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CommentThread(Base):
    __tablename__ = "comment_threads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"))
    stage_type: Mapped[str] = mapped_column(String(80), nullable=False)
    artifact_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("artifacts.id"), nullable=True
    )
    artifact_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("artifacts.id"), nullable=True
    )
    target_type: Mapped[str] = mapped_column(String(50), nullable=False, default="block")
    target_id: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="open")
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    messages: Mapped[list[CommentMessage]] = relationship(
        "CommentMessage", back_populates="thread", cascade="all, delete-orphan"
    )


class CommentMessage(Base):
    __tablename__ = "comment_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("comment_threads.id", ondelete="CASCADE")
    )
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    message_type: Mapped[str] = mapped_column(String(50), nullable=False, default="comment")
    decision: Mapped[str] = mapped_column(String(50), nullable=False, default="none")
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    thread: Mapped[CommentThread] = relationship("CommentThread", back_populates="messages")

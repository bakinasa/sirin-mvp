"""Pipeline v2: sources, chat, patches, comments, artifact version metadata.

Revision ID: 003_pipeline_v2
Revises: 002_user_models
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003_pipeline_v2"
down_revision: Union[str, None] = "002_user_models"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "artifacts",
        sa.Column("change_type", sa.String(50), nullable=False, server_default="ai_generate"),
    )
    op.add_column(
        "artifacts",
        sa.Column("change_summary", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "artifacts",
        sa.Column("frozen", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "project_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("title", sa.String(500), nullable=False, server_default=""),
        sa.Column("source_type", sa.String(80), nullable=False, server_default="other"),
        sa.Column("file_path", sa.String(1000), nullable=False, server_default=""),
        sa.Column("mime_type", sa.String(255), nullable=False, server_default=""),
        sa.Column("parsed_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("parse_status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("parse_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("summary_short_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("summary_structured_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("important_chunks_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_project_sources_project_id", "project_sources", ["project_id"])

    op.create_table(
        "project_source_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("project_sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("page_ref", sa.String(80), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_project_source_chunks_source_id", "project_source_chunks", ["source_id"])

    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_project_source_chunks_text_trgm "
        "ON project_source_chunks USING gin (text gin_trgm_ops)"
    )

    op.create_table(
        "artifact_patches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("stage_type", sa.String(80), nullable=False),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("artifacts.id"), nullable=True),
        sa.Column("artifact_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("artifacts.id"), nullable=True),
        sa.Column("scope", sa.String(50), nullable=False, server_default="local"),
        sa.Column("target_id", sa.String(120), nullable=False, server_default=""),
        sa.Column("instruction", sa.Text(), nullable=False, server_default=""),
        sa.Column("patch_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_artifact_patches_project_id", "artifact_patches", ["project_id"])

    op.create_table(
        "stage_chat_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("stage_type", sa.String(80), nullable=False),
        sa.Column("mode", sa.String(50), nullable=False, server_default="ask"),
        sa.Column("summary_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_stage_chat_sessions_project_stage", "stage_chat_sessions", ["project_id", "stage_type"])

    op.create_table(
        "stage_chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stage_chat_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("applied_patch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("artifact_patches.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_stage_chat_messages_session_id", "stage_chat_messages", ["session_id"])

    op.create_table(
        "comment_threads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("stage_type", sa.String(80), nullable=False),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("artifacts.id"), nullable=True),
        sa.Column("artifact_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("artifacts.id"), nullable=True),
        sa.Column("target_type", sa.String(50), nullable=False, server_default="block"),
        sa.Column("target_id", sa.String(120), nullable=False, server_default=""),
        sa.Column("status", sa.String(50), nullable=False, server_default="open"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_comment_threads_project_stage", "comment_threads", ["project_id", "stage_type"])

    op.create_table(
        "comment_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "thread_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("comment_threads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("message_type", sa.String(50), nullable=False, server_default="comment"),
        sa.Column("decision", sa.String(50), nullable=False, server_default="none"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_comment_messages_thread_id", "comment_messages", ["thread_id"])


def downgrade() -> None:
    op.drop_index("ix_comment_messages_thread_id", table_name="comment_messages")
    op.drop_table("comment_messages")
    op.drop_index("ix_comment_threads_project_stage", table_name="comment_threads")
    op.drop_table("comment_threads")
    op.drop_index("ix_stage_chat_messages_session_id", table_name="stage_chat_messages")
    op.drop_table("stage_chat_messages")
    op.drop_index("ix_stage_chat_sessions_project_stage", table_name="stage_chat_sessions")
    op.drop_table("stage_chat_sessions")
    op.drop_index("ix_artifact_patches_project_id", table_name="artifact_patches")
    op.drop_table("artifact_patches")
    op.execute("DROP INDEX IF EXISTS ix_project_source_chunks_text_trgm")
    op.drop_index("ix_project_source_chunks_source_id", table_name="project_source_chunks")
    op.drop_table("project_source_chunks")
    op.drop_index("ix_project_sources_project_id", table_name="project_sources")
    op.drop_table("project_sources")
    op.drop_column("artifacts", "frozen")
    op.drop_column("artifacts", "change_summary")
    op.drop_column("artifacts", "change_type")

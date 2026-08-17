"""Add summary_job_json for background source summarization.

Revision ID: 004_source_summary_jobs
Revises: 003_pipeline_v2
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004_source_summary_jobs"
down_revision: Union[str, None] = "003_pipeline_v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "project_sources",
        sa.Column(
            "summary_job_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("project_sources", "summary_job_json")

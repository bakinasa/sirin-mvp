"""Add user_models + remove model_catalog_items

Revision ID: 002_user_models
Revises: 001_initial
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002_user_models"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_models",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("provider_type", sa.String(length=80), nullable=False),
        sa.Column("provider_name", sa.String(length=255), nullable=False, server_default="Custom"),
        sa.Column("base_url", sa.String(length=500), nullable=False),
        sa.Column("capabilities_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("encrypted_api_key", sa.Text(), nullable=False),
        sa.Column("model_id", sa.String(length=255), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("is_free", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("input_price", sa.Float(), nullable=True),
        sa.Column("output_price", sa.Float(), nullable=True),
        sa.Column("context_window", sa.Integer(), nullable=True),
        sa.Column("tags", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "owner_id",
            "provider_type",
            "base_url",
            "model_id",
            name="uq_user_provider_model",
        ),
    )

    # Migrate existing catalog models into per-user user_models (best-effort).
    # Old tables had no owner_id on model_catalog_items, so we duplicate per active
    # provider_credentials for each user.
    #
    # IMPORTANT: we set user_models.id = model_catalog_items.id to keep existing
    # FK values in step_model_configs stable (assuming single active user per DB
    # in the MVP). If multiple users sync the same provider, ids may collide.
    op.execute(
        """
        INSERT INTO user_models (
            id,
            owner_id,
            provider_type,
            provider_name,
            base_url,
            capabilities_json,
            encrypted_api_key,
            model_id,
            label,
            is_free,
            input_price,
            output_price,
            context_window,
            tags,
            is_enabled
        )
        SELECT
            mci.id,
            pc.owner_id,
            mp.type,
            mp.name,
            mp.base_url,
            mci.capabilities_json,
            pc.encrypted_secret,
            mci.model_id,
            mci.label,
            mci.is_free,
            mci.input_price,
            mci.output_price,
            mci.context_window,
            mci.tags,
            mci.is_enabled
        FROM model_catalog_items mci
        JOIN model_providers mp ON mp.id = mci.provider_id
        JOIN provider_credentials pc
          ON pc.provider_id = mp.id
         AND pc.is_active = TRUE
        """
    )

    # Update StepModelConfig foreign keys to point to user_models instead of model_catalog_items.
    # The default FK names are expected from SQLAlchemy/Alembic:
    # - step_model_configs_primary_model_id_fkey
    # - step_model_configs_fallback_model_id_fkey
    op.drop_constraint(
        "step_model_configs_primary_model_id_fkey",
        "step_model_configs",
        type_="foreignkey",
    )
    op.drop_constraint(
        "step_model_configs_fallback_model_id_fkey",
        "step_model_configs",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "step_model_configs_primary_model_id_fkey",
        "step_model_configs",
        "user_models",
        ["primary_model_id"],
        ["id"],
    )
    op.create_foreign_key(
        "step_model_configs_fallback_model_id_fkey",
        "step_model_configs",
        "user_models",
        ["fallback_model_id"],
        ["id"],
    )

    # Catalog is no longer used.
    op.drop_table("model_catalog_items")


def downgrade() -> None:
    # Re-create the old catalog table (best-effort; existing data is not restored).
    op.create_table(
        "model_catalog_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("model_providers.id")),
        sa.Column("model_id", sa.String(length=255), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("is_free", sa.Boolean(), nullable=False),
        sa.Column("input_price", sa.Float(), nullable=True),
        sa.Column("output_price", sa.Float(), nullable=True),
        sa.Column("context_window", sa.Integer(), nullable=True),
        sa.Column("capabilities_json", postgresql.JSONB(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("tags", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("provider_id", "model_id", name="uq_provider_model"),
    )

    # Restore StepModelConfig foreign keys back to model_catalog_items.
    op.drop_constraint(
        "step_model_configs_primary_model_id_fkey",
        "step_model_configs",
        type_="foreignkey",
    )
    op.drop_constraint(
        "step_model_configs_fallback_model_id_fkey",
        "step_model_configs",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "step_model_configs_primary_model_id_fkey",
        "step_model_configs",
        "model_catalog_items",
        ["primary_model_id"],
        ["id"],
    )
    op.create_foreign_key(
        "step_model_configs_fallback_model_id_fkey",
        "step_model_configs",
        "model_catalog_items",
        ["fallback_model_id"],
        ["id"],
    )

    op.drop_table("user_models")


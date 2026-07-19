"""Add created_at to model_registry table

Revision ID: 0003_model_registry_created_at
Revises: 0002_dataset_versioning
Create Date: 2026-07-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_model_registry_created_at"
down_revision = "0002_dataset_versioning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add created_at with a sensible default for existing rows
    op.add_column(
        "model_registry",
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=True,
            server_default=sa.text("NOW()"),
        ),
    )


def downgrade() -> None:
    op.drop_column("model_registry", "created_at")

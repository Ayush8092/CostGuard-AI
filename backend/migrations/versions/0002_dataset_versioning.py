"""dataset versioning — adds upload_mode, active_flag, dataset_name to
uploaded_datasets; adds dataset_id FK to all ML output tables;
creates executive_insights table.

Revision ID: 0002_dataset_versioning
Revises: 0001_initial
Create Date: 2026-07-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_dataset_versioning"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # UploadedDataset new columns
    op.add_column("uploaded_datasets",
        sa.Column("dataset_name", sa.String(255), nullable=True))
    op.add_column("uploaded_datasets",
        sa.Column("upload_mode", sa.String(30),
                  server_default="continuous", nullable=False))
    op.add_column("uploaded_datasets",
        sa.Column("active_flag", sa.Boolean(),
                  server_default=sa.false(), nullable=False))

    # dataset_id FK on all ML output tables
    for table in ["forecast_results","anomalies","waste_classifications",
                  "recommendations","weekly_reports","incident_scores"]:
        op.add_column(table,
            sa.Column("dataset_id", postgresql.UUID(as_uuid=False), nullable=True))
        op.create_index(f"ix_{table}_dataset_id", table, ["dataset_id"])

    # ProcessedTelemetry: add dataset_id FK column
    op.add_column("processed_telemetry",
        sa.Column("dataset_id", postgresql.UUID(as_uuid=False), nullable=True))
    op.create_index("ix_processed_telemetry_dataset_id",
                    "processed_telemetry", ["dataset_id"])
    op.create_foreign_key(
        "fk_processed_telemetry_dataset_id",
        "processed_telemetry", "uploaded_datasets",
        ["dataset_id"], ["id"],
        ondelete="SET NULL",
    )

    # Executive insights table
    op.create_table(
        "executive_insights",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("uploaded_datasets.id"), nullable=False),
        sa.Column("insight_text", sa.Text(), nullable=False),
        sa.Column("metrics_snapshot", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_executive_insights_org",
                    "executive_insights", ["organization_id"])
    op.create_index("ix_executive_insights_dataset",
                    "executive_insights", ["dataset_id"])


def downgrade() -> None:
    op.drop_table("executive_insights")
    op.drop_constraint("fk_processed_telemetry_dataset_id",
                       "processed_telemetry", type_="foreignkey")
    op.drop_index("ix_processed_telemetry_dataset_id",
                  table_name="processed_telemetry")
    op.drop_column("processed_telemetry", "dataset_id")
    for table in ["forecast_results","anomalies","waste_classifications",
                  "recommendations","weekly_reports","incident_scores"]:
        op.drop_index(f"ix_{table}_dataset_id", table_name=table)
        op.drop_column(table, "dataset_id")
    op.drop_column("uploaded_datasets", "active_flag")
    op.drop_column("uploaded_datasets", "upload_mode")
    op.drop_column("uploaded_datasets", "dataset_name")

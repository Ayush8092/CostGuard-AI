"""Add all missing columns that 0002/0003 may have skipped.

Safe to run on any partially-migrated database — every ADD COLUMN
uses IF NOT EXISTS so it never errors if the column already exists.

Revision ID: 0004_add_missing_columns
Revises: 0003_model_registry_created_at
Create Date: 2026-07-18
"""
from alembic import op
import sqlalchemy as sa


revision = "0004_add_missing_columns"
down_revision = "0003_model_registry_created_at"
branch_labels = None
depends_on = None


def _col(table: str, column: str, col_type: str,
         nullable: bool = True, default: str | None = None) -> None:
    """ADD COLUMN IF NOT EXISTS — never errors if column already exists."""
    default_clause = f"DEFAULT {default}" if default else ""
    null_clause = "NULL" if nullable else f"NOT NULL {default_clause}"
    op.execute(sa.text(
        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type} {null_clause}"
    ))


def _index(name: str, table: str, column: str) -> None:
    """CREATE INDEX IF NOT EXISTS — never errors if index already exists."""
    op.execute(sa.text(
        f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({column})"
    ))


def _fk(constraint_name: str, src_table: str, src_col: str,
        ref_table: str, ref_col: str) -> None:
    """Add FK only if it doesn't already exist."""
    op.execute(sa.text(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = '{constraint_name}'
                AND table_name = '{src_table}'
            ) THEN
                ALTER TABLE {src_table}
                ADD CONSTRAINT {constraint_name}
                FOREIGN KEY ({src_col}) REFERENCES {ref_table}({ref_col})
                ON DELETE SET NULL;
            END IF;
        END $$;
    """))


def upgrade() -> None:

    # ── uploaded_datasets ─────────────────────────────────────────────────
    _col("uploaded_datasets", "dataset_name", "VARCHAR(255)")
    _col("uploaded_datasets", "upload_mode",  "VARCHAR(30)",
         nullable=False, default="'continuous'")
    _col("uploaded_datasets", "active_flag",  "BOOLEAN",
         nullable=False, default="FALSE")

    # ── processed_telemetry ───────────────────────────────────────────────
    _col("processed_telemetry", "dataset_id", "UUID")
    _fk("fk_processed_telemetry_dataset_id",
        "processed_telemetry", "dataset_id",
        "uploaded_datasets", "id")
    _index("ix_processed_telemetry_dataset_id",
           "processed_telemetry", "dataset_id")

    # ── ML output tables — add dataset_id FK column ───────────────────────
    for table in [
        "forecast_results",
        "anomalies",
        "waste_classifications",
        "recommendations",
        "weekly_reports",
        "incident_scores",
    ]:
        _col(table, "dataset_id", "UUID")
        _index(f"ix_{table}_dataset_id", table, "dataset_id")

    # ── model_registry.created_at ─────────────────────────────────────────
    _col("model_registry", "created_at", "TIMESTAMP")

    # ── executive_insights table ──────────────────────────────────────────
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS executive_insights (
            id              UUID            PRIMARY KEY,
            organization_id UUID            NOT NULL
                            REFERENCES organizations(id),
            dataset_id      UUID            NOT NULL
                            REFERENCES uploaded_datasets(id),
            insight_text    TEXT            NOT NULL,
            metrics_snapshot JSONB,
            created_at      TIMESTAMP
        )
    """))
    _index("ix_executive_insights_org",
           "executive_insights", "organization_id")
    _index("ix_executive_insights_dataset",
           "executive_insights", "dataset_id")


def downgrade() -> None:
    # Intentionally not implemented.
    # This is a recovery migration. Rolling it back would require
    # knowing exactly which columns existed before the partial migration,
    # which is impossible to determine safely in the general case.
    pass
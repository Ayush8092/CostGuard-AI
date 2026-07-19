"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-28

This migration creates the full CostGuard AI schema (Part 7). It mirrors
app/db/models.py exactly - if you change a model, run:
    alembic revision --autogenerate -m "describe your change"
to generate the next migration instead of hand-editing this file.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime()),
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255)),
        sa.Column("role", sa.String(20), nullable=False, server_default="viewer"),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_users_organization_id", "users", ["organization_id"])

    op.create_table(
        "uploaded_datasets",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id")),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("storage_path", sa.String(1000), nullable=False),
        sa.Column("status", sa.String(20), server_default="queued"),
        sa.Column("progress_pct", sa.Integer(), server_default="0"),
        sa.Column("row_count", sa.Integer()),
        sa.Column("column_mapping", postgresql.JSONB()),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("processed_at", sa.DateTime()),
    )
    op.create_index("ix_uploaded_datasets_organization_id", "uploaded_datasets", ["organization_id"])

    op.create_table(
        "processed_telemetry",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("source_tier", sa.String(20), nullable=False),
        sa.Column("dataset_version", sa.String(50)),
        sa.Column("date", sa.DateTime(), nullable=False),
        sa.Column("account_id", sa.String(100)),
        sa.Column("service", sa.String(100), nullable=False),
        sa.Column("resource_id", sa.String(200), nullable=False),
        sa.Column("instance_type", sa.String(100)),
        sa.Column("region", sa.String(100)),
        sa.Column("cost", sa.Float(), nullable=False),
        sa.Column("usage_hours", sa.Float()),
        sa.Column("cpu_avg_pct", sa.Float()),
        sa.Column("memory_avg_pct", sa.Float()),
        sa.Column("disk_io", sa.Float()),
        sa.Column("network_io", sa.Float()),
        sa.Column("runtime_days", sa.Integer()),
        sa.Column("cost_growth_rate", sa.Float()),
        sa.Column("anomaly_history_count", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_telemetry_organization_id", "processed_telemetry", ["organization_id"])
    op.create_index("ix_telemetry_resource_id", "processed_telemetry", ["resource_id"])
    op.create_index("ix_telemetry_date", "processed_telemetry", ["date"])
    op.create_index("ix_telemetry_service", "processed_telemetry", ["service"])
    op.create_index("ix_telemetry_account_id", "processed_telemetry", ["account_id"])

    op.create_table(
        "pricing_catalog",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("instance_type", sa.String(100), nullable=False),
        sa.Column("vcpu", sa.Integer()),
        sa.Column("ram_gb", sa.Float()),
        sa.Column("region", sa.String(100)),
        sa.Column("os", sa.String(100)),
        sa.Column("pricing_type", sa.String(20)),
        sa.Column("hourly_rate", sa.Float(), nullable=False),
        sa.Column("source_file", sa.String(500)),
        sa.Column("effective_date", sa.DateTime()),
        sa.Column("created_at", sa.DateTime()),
        sa.UniqueConstraint("instance_type", "region", "os", "pricing_type", "effective_date", name="uq_pricing_row"),
    )
    op.create_index("ix_pricing_instance_type", "pricing_catalog", ["instance_type"])
    op.create_index("ix_pricing_region", "pricing_catalog", ["region"])

    op.create_table(
        "feature_store",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("resource_id", sa.String(200), nullable=False),
        sa.Column("date", sa.DateTime(), nullable=False),
        sa.Column("feature_version", sa.String(20), server_default="v1"),
        sa.Column("features", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime()),
        sa.UniqueConstraint("organization_id", "resource_id", "date", "feature_version", name="uq_feature_row"),
    )
    op.create_index("ix_feature_store_organization_id", "feature_store", ["organization_id"])
    op.create_index("ix_feature_store_resource_id", "feature_store", ["resource_id"])
    op.create_index("ix_feature_store_date", "feature_store", ["date"])

    op.create_table(
        "forecast_results",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("level", sa.String(20), nullable=False),
        sa.Column("service", sa.String(100)),
        sa.Column("forecast_date", sa.DateTime(), nullable=False),
        sa.Column("forecast", sa.Float(), nullable=False),
        sa.Column("ci_lower", sa.Float(), nullable=False),
        sa.Column("ci_upper", sa.Float(), nullable=False),
        sa.Column("model_version", sa.String(50)),
        sa.Column("naive_baseline", sa.Float()),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_forecast_organization_id", "forecast_results", ["organization_id"])
    op.create_index("ix_forecast_date", "forecast_results", ["forecast_date"])
    op.create_index("ix_forecast_service", "forecast_results", ["service"])

    op.create_table(
        "anomalies",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("resource_id", sa.String(200), nullable=False),
        sa.Column("date", sa.DateTime(), nullable=False),
        sa.Column("dimension_scores", postgresql.JSONB()),
        sa.Column("incident_score", sa.Float(), nullable=False),
        sa.Column("severity", sa.String(20)),
        sa.Column("is_ground_truth_eval", sa.Boolean(), server_default=sa.false()),
        sa.Column("model_version", sa.String(50)),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_anomalies_organization_id", "anomalies", ["organization_id"])
    op.create_index("ix_anomalies_resource_id", "anomalies", ["resource_id"])
    op.create_index("ix_anomalies_date", "anomalies", ["date"])

    op.create_table(
        "incident_scores",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("date", sa.DateTime(), nullable=False),
        sa.Column("avg_incident_score", sa.Float()),
        sa.Column("high_severity_count", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_incident_scores_organization_id", "incident_scores", ["organization_id"])

    op.create_table(
        "waste_classifications",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("resource_id", sa.String(200), nullable=False),
        sa.Column("date", sa.DateTime(), nullable=False),
        sa.Column("waste_score", sa.Float(), nullable=False),
        sa.Column("bucket", sa.String(30)),
        sa.Column("predicted_bucket", sa.String(30)),
        sa.Column("shap_top_features", postgresql.JSONB()),
        sa.Column("model_version", sa.String(50)),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_waste_organization_id", "waste_classifications", ["organization_id"])
    op.create_index("ix_waste_resource_id", "waste_classifications", ["resource_id"])
    op.create_index("ix_waste_date", "waste_classifications", ["date"])

    op.create_table(
        "recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("resource_id", sa.String(200), nullable=False),
        sa.Column("action", sa.String(255), nullable=False),
        sa.Column("estimated_savings", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("supporting_rule", sa.String(255)),
        sa.Column("impact_tier", sa.String(20)),
        sa.Column("impact_score", sa.Float()),
        sa.Column("citation_chunk_ids", postgresql.JSONB()),
        sa.Column("status", sa.String(20), server_default="open"),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_recommendations_organization_id", "recommendations", ["organization_id"])
    op.create_index("ix_recommendations_resource_id", "recommendations", ["resource_id"])

    op.create_table(
        "model_registry",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("model_type", sa.String(50), nullable=False),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("training_date", sa.DateTime()),
        sa.Column("hyperparameters", postgresql.JSONB()),
        sa.Column("evaluation_metrics", postgresql.JSONB()),
        sa.Column("feature_set", postgresql.JSONB()),
        sa.Column("dataset_version", sa.String(50)),
        sa.Column("artifact_path", sa.String(1000)),
        sa.Column("is_active", sa.Boolean(), server_default=sa.false()),
    )
    op.create_index("ix_model_registry_model_type", "model_registry", ["model_type"])

    op.create_table(
        "weekly_reports",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("period_start", sa.DateTime(), nullable=False),
        sa.Column("period_end", sa.DateTime(), nullable=False),
        sa.Column("metrics_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("narrative", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_weekly_reports_organization_id", "weekly_reports", ["organization_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("severity", sa.String(20), server_default="info"),
        sa.Column("details", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_audit_logs_organization_id", "audit_logs", ["organization_id"])

    op.create_table(
        "aws_account_connections",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("aws_account_id", sa.String(20), nullable=False),
        sa.Column("role_arn", sa.String(255), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
        sa.Column("last_synced_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_aws_accounts_organization_id", "aws_account_connections", ["organization_id"])


def downgrade() -> None:
    op.drop_table("aws_account_connections")
    op.drop_table("audit_logs")
    op.drop_table("weekly_reports")
    op.drop_table("model_registry")
    op.drop_table("recommendations")
    op.drop_table("waste_classifications")
    op.drop_table("incident_scores")
    op.drop_table("anomalies")
    op.drop_table("forecast_results")
    op.drop_table("feature_store")
    op.drop_table("pricing_catalog")
    op.drop_table("processed_telemetry")
    op.drop_table("uploaded_datasets")
    op.drop_table("users")
    op.drop_table("organizations")

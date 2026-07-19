"""
db/models.py — SQLAlchemy ORM models for CostGuard AI.

Key change for Feature 1+2: UploadedDataset now has:
  - dataset_name   : human-readable label
  - upload_mode    : "new_analysis" | "continuous"
  - active_flag    : which dataset the dashboard currently shows
  - ProcessedTelemetry.dataset_id links rows to a specific UploadedDataset
    (replaces the old loose string field dataset_version)
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Multi-tenancy ────────────────────────────────────────────────────────

class Organization(Base):
    __tablename__ = "organizations"
    id         = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name       = Column(String(255), nullable=False, unique=True)
    created_at = Column(DateTime, default=_now)

    users    = relationship("User",             back_populates="organization")
    datasets = relationship("UploadedDataset",  back_populates="organization")


class User(Base):
    __tablename__ = "users"
    id              = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    organization_id = Column(UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=False)
    email           = Column(String(255), nullable=False, unique=True, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name       = Column(String(255))
    role            = Column(String(20), default="viewer")   # admin | analyst | viewer
    is_active       = Column(Boolean, default=True)
    created_at      = Column(DateTime, default=_now)

    organization = relationship("Organization", back_populates="users")


# ── Dataset management (Feature 1 + 2) ──────────────────────────────────

class UploadedDataset(Base):
    __tablename__ = "uploaded_datasets"

    id                  = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    organization_id     = Column(UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=False, index=True)
    uploaded_by_user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"))

    # ── New columns for Feature 1+2 ──────────────────────────────────────
    dataset_name  = Column(String(255))           # human-readable label, e.g. "AWS June 2024"
    upload_mode   = Column(String(30), default="continuous")  # "new_analysis" | "continuous"
    active_flag   = Column(Boolean, default=False)            # True = this is the active dataset
    # ─────────────────────────────────────────────────────────────────────

    original_filename = Column(String(512))
    storage_path      = Column(String(1024))
    status            = Column(String(20), default="queued")  # queued|processing|done|failed
    progress_pct      = Column(Integer, default=0)
    row_count         = Column(Integer)
    column_mapping    = Column(JSONB)
    error_message     = Column(Text)
    created_at        = Column(DateTime, default=_now)
    processed_at      = Column(DateTime)

    organization = relationship("Organization", back_populates="datasets")
    telemetry    = relationship("ProcessedTelemetry", back_populates="dataset",
                                foreign_keys="ProcessedTelemetry.dataset_id")


# ── Core telemetry (links to dataset via dataset_id FK) ─────────────────

class ProcessedTelemetry(Base):
    __tablename__ = "processed_telemetry"
    __table_args__ = (
        UniqueConstraint("organization_id", "resource_id", "date", "dataset_id",
                         name="uq_telemetry_org_resource_date_dataset"),
    )

    id              = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    organization_id = Column(UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=False, index=True)

    # FK to UploadedDataset — replaces the old loose "dataset_version" string
    dataset_id      = Column(UUID(as_uuid=False), ForeignKey("uploaded_datasets.id"), nullable=True, index=True)

    # kept for backward compat with seed_data.py which uses "synthetic" / "bitbrains"
    source_tier     = Column(String(30), default="csv_upload")
    dataset_version = Column(String(128))  # legacy — prefer dataset_id going forward

    date            = Column(DateTime, nullable=False, index=True)
    account_id      = Column(String(128))
    service         = Column(String(128), index=True)
    resource_id     = Column(String(256), nullable=False, index=True)
    instance_type   = Column(String(128))
    region          = Column(String(64))
    cost            = Column(Float)
    usage_hours     = Column(Float)
    cpu_avg_pct     = Column(Float)
    memory_avg_pct  = Column(Float)
    disk_io         = Column(Float)
    network_io      = Column(Float)
    runtime_days    = Column(Integer)
    cost_growth_rate= Column(Float)
    anomaly_history_count = Column(Integer, default=0)

    dataset = relationship("UploadedDataset", back_populates="telemetry",
                           foreign_keys=[dataset_id])


# ── ML output tables ─────────────────────────────────────────────────────

class ForecastResult(Base):
    __tablename__ = "forecast_results"
    id              = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    organization_id = Column(UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=False, index=True)
    dataset_id      = Column(UUID(as_uuid=False), ForeignKey("uploaded_datasets.id"), nullable=True, index=True)
    level           = Column(String(20))        # org_total | per_service
    service         = Column(String(128))
    forecast_date   = Column(DateTime, index=True)
    forecast        = Column(Float)
    ci_lower        = Column(Float)
    ci_upper        = Column(Float)
    naive_baseline  = Column(Float)
    model_version   = Column(String(128))


class Anomaly(Base):
    __tablename__ = "anomalies"
    id              = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    organization_id = Column(UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=False, index=True)
    dataset_id      = Column(UUID(as_uuid=False), ForeignKey("uploaded_datasets.id"), nullable=True, index=True)
    resource_id     = Column(String(256), index=True)
    date            = Column(DateTime, index=True)
    dimension_scores= Column(JSONB)
    incident_score  = Column(Float)
    severity        = Column(String(20))
    is_ground_truth_eval = Column(Boolean, default=False)
    model_version   = Column(String(128))


class IncidentScore(Base):
    __tablename__ = "incident_scores"
    id                  = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    organization_id     = Column(UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=False, index=True)
    dataset_id          = Column(UUID(as_uuid=False), ForeignKey("uploaded_datasets.id"), nullable=True)
    date                = Column(DateTime, index=True)
    avg_incident_score  = Column(Float)
    high_severity_count = Column(Integer)


class WasteClassification(Base):
    __tablename__ = "waste_classifications"
    id              = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    organization_id = Column(UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=False, index=True)
    dataset_id      = Column(UUID(as_uuid=False), ForeignKey("uploaded_datasets.id"), nullable=True, index=True)
    resource_id     = Column(String(256), index=True)
    date            = Column(DateTime, index=True)
    waste_score     = Column(Float)
    bucket          = Column(String(30))
    predicted_bucket= Column(String(30))
    shap_top_features = Column(JSONB)
    model_version   = Column(String(128))


class Recommendation(Base):
    __tablename__ = "recommendations"
    id                  = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    organization_id     = Column(UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=False, index=True)
    dataset_id          = Column(UUID(as_uuid=False), ForeignKey("uploaded_datasets.id"), nullable=True, index=True)
    resource_id         = Column(String(256))
    action              = Column(Text)
    estimated_savings   = Column(Float)
    confidence          = Column(Float)
    reason              = Column(Text)
    supporting_rule     = Column(Text)
    impact_tier         = Column(String(20))
    impact_score        = Column(Float)
    citation_chunk_ids  = Column(JSONB)
    status              = Column(String(20), default="open")
    created_at          = Column(DateTime, default=_now)


class WeeklyReport(Base):
    __tablename__ = "weekly_reports"
    id              = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    organization_id = Column(UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=False, index=True)
    dataset_id      = Column(UUID(as_uuid=False), ForeignKey("uploaded_datasets.id"), nullable=True, index=True)
    period_start    = Column(String(20))
    period_end      = Column(String(20))
    narrative       = Column(Text)
    metrics_snapshot= Column(JSONB)
    created_at      = Column(DateTime, default=_now)


class ExecutiveInsight(Base):
    __tablename__ = "executive_insights"
    id              = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    organization_id = Column(UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=False, index=True)
    dataset_id      = Column(UUID(as_uuid=False), ForeignKey("uploaded_datasets.id"), nullable=False, index=True)
    insight_text    = Column(Text, nullable=False)
    metrics_snapshot= Column(JSONB)
    created_at      = Column(DateTime, default=_now)


# ── MLOps ────────────────────────────────────────────────────────────────

class ModelRegistry(Base):
    __tablename__ = "model_registry"
    id                  = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    model_type          = Column(String(50), nullable=False, index=True)
    version             = Column(String(128), nullable=False)
    training_date       = Column(DateTime, default=_now)
    hyperparameters     = Column(JSONB)
    evaluation_metrics  = Column(JSONB)
    feature_set         = Column(JSONB)
    dataset_version     = Column(String(128))
    artifact_path       = Column(String(1024))
    is_active           = Column(Boolean, default=False)
    created_at          = Column(DateTime, default=_now)


class FeatureStore(Base):
    __tablename__ = "feature_store"
    __table_args__ = (
        UniqueConstraint("organization_id", "resource_id", "feature_date", "feature_set_version",
                         name="uq_feature_row"),
    )
    id                   = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    organization_id      = Column(UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=False, index=True)
    resource_id          = Column(String(256), nullable=False)
    feature_date         = Column(DateTime, nullable=False)
    feature_set_version  = Column(String(64), nullable=False)
    features             = Column(JSONB, nullable=False)
    computed_at          = Column(DateTime, default=_now)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id              = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    organization_id = Column(UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=False, index=True)
    event_type      = Column(String(100), nullable=False)
    severity        = Column(String(20), default="info")
    details         = Column(JSONB)
    created_at      = Column(DateTime, default=_now, index=True)

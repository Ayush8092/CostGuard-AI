"""
Model Registry / Experiment Tracking (Part 6) - self-built, MLflow-like
BY FUNCTION. This module does not use and does not claim to use MLflow
or any other third-party experiment tracking tool; it is a thin,
purpose-built layer over the model_registry table (Part 7).

For every trained model version, logs: version number, model type,
training date, hyperparameters, evaluation metrics, feature set used,
and dataset version (tying back to Part 1's dataset versioning).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import ModelRegistry


@dataclass
class ModelRegistryEntry:
    model_type: str  # forecast | anomaly | waste_classifier
    version: str
    hyperparameters: dict
    evaluation_metrics: dict
    feature_set: list[str]
    dataset_version: str
    artifact_path: str | None = None
    training_date: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = False


def register_model(db: Session, entry: ModelRegistryEntry) -> str:
    """Writes one model_registry row and returns its id."""
    record_id = str(uuid.uuid4())
    db.add(ModelRegistry(
        id=record_id,
        model_type=entry.model_type,
        version=entry.version,
        training_date=entry.training_date,
        hyperparameters=entry.hyperparameters,
        evaluation_metrics=entry.evaluation_metrics,
        feature_set=entry.feature_set,
        dataset_version=entry.dataset_version,
        artifact_path=entry.artifact_path,
        is_active=entry.is_active,
    ))
    db.commit()
    return record_id


def promote_model_to_active(db: Session, model_type: str, version: str) -> None:
    """Deactivates all other versions of this model_type, activates the given version."""
    db.query(ModelRegistry).filter(ModelRegistry.model_type == model_type).update({"is_active": False})
    db.query(ModelRegistry).filter(
        ModelRegistry.model_type == model_type, ModelRegistry.version == version
    ).update({"is_active": True})
    db.commit()


def get_active_model(db: Session, model_type: str) -> ModelRegistry | None:
    return db.query(ModelRegistry).filter(
        ModelRegistry.model_type == model_type, ModelRegistry.is_active.is_(True)
    ).first()


def list_registry(db: Session, model_type: str | None = None) -> list[ModelRegistry]:
    """Backs the GET /models/registry endpoint."""
    query = db.query(ModelRegistry).order_by(ModelRegistry.training_date.desc())
    if model_type:
        query = query.filter(ModelRegistry.model_type == model_type)
    return query.all()


def registry_entry_to_dict(entry: ModelRegistry) -> dict:
    return {
        "id": entry.id,
        "model_type": entry.model_type,
        "version": entry.version,
        "training_date": entry.training_date.isoformat() if entry.training_date else None,
        "hyperparameters": entry.hyperparameters,
        "evaluation_metrics": entry.evaluation_metrics,
        "feature_set": entry.feature_set,
        "dataset_version": entry.dataset_version,
        "artifact_path": entry.artifact_path,
        "is_active": entry.is_active,
    }


if __name__ == "__main__":
    # Verify the registry SQL compiles correctly against the Postgres
    # dialect without needing a live DB connection (consistent with how
    # the rest of this project's DB-layer code has been spot-checked).
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateTable
    from app.db.models import ModelRegistry as MRModel

    ddl = str(CreateTable(MRModel.__table__).compile(dialect=postgresql.dialect()))
    assert "CREATE TABLE model_registry" in ddl
    print("model_registry DDL compiles correctly against Postgres dialect.")
    print()
    print("Example registry entry that would be logged after training the forecaster:")
    example = ModelRegistryEntry(
        model_type="forecast",
        version="v1.0.0",
        hyperparameters={"n_estimators": 150, "max_depth": 4, "learning_rate": 0.08, "quantiles": [0.05, 0.5, 0.95]},
        evaluation_metrics={"mae": 3.03, "rmse": 4.08, "mape": 2.69, "naive_mape": 8.64, "error_reduction_pct": 68.93},
        feature_set=["day_of_week", "day_of_month", "rolling_avg_7d", "rolling_avg_30d", "lag_1d", "lag_7d", "active_resource_count"],
        dataset_version="synthetic_v1",
        is_active=True,
    )
    for k, v in vars(example).items():
        print(f"  {k}: {v}")

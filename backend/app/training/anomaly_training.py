"""
Anomaly detector training pipeline (app/training/anomaly_training.py).

Called ONLY on initial setup, drift detection, or weekly schedule.
NOT called on every nightly job.

The per-dimension Isolation Forest models are trained here and saved as
one artifact. Nightly inference loads this artifact and calls
.predict() without retraining.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from loguru import logger
from sqlalchemy.orm import Session

from app.mlops.model_registry import ModelRegistryEntry, promote_model_to_active, register_model
from app.models.anomaly_detection import (
    DIMENSIONS,
    INCIDENT_SCORE_WEIGHTS,
    SEVERITY_BANDS,
    _add_resource_relative_features,
    fit_dimension_models,
)
from app.training.model_store import cleanup_old_artifacts, save_model


def train_anomaly_model(
    db: Session,
    billing_df: pd.DataFrame,
    dataset_version: str,
    contamination: float = 0.05,
) -> dict:
    """
    Trains per-dimension Isolation Forest models, saves artifact,
    registers in model registry, promotes to active.
    """
    version_tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    version = f"{dataset_version}_{version_tag}"

    try:
        featured_df = _add_resource_relative_features(billing_df, DIMENSIONS)
        models = fit_dimension_models(featured_df, contamination=contamination)

        if not models:
            return {"status": "skipped", "reason": "no dimensions had sufficient data"}

        # Bundle everything the inference pipeline needs in one artifact
        artifact = {
            "dimension_models": models,
            "dimensions_used": list(models.keys()),
            "contamination": contamination,
            "incident_score_weights": INCIDENT_SCORE_WEIGHTS,
            "severity_bands": SEVERITY_BANDS,
        }

        artifact_path = save_model("anomaly", artifact, version=version)

        register_model(db, ModelRegistryEntry(
            model_type="anomaly",
            version=version,
            hyperparameters={"contamination": contamination, "n_estimators": 150},
            evaluation_metrics={"dimensions_trained": len(models), "note": "unsupervised_no_ground_truth_on_real_data"},
            feature_set=list(models.keys()),
            dataset_version=dataset_version,
            artifact_path=artifact_path,
            is_active=True,
        ))
        promote_model_to_active(db, "anomaly", version)
        cleanup_old_artifacts("anomaly", keep_last=3)

        logger.info(f"Anomaly training complete: dimensions={list(models.keys())}")
        return {
            "status": "trained",
            "version": version,
            "artifact_path": artifact_path,
            "dimensions": list(models.keys()),
        }

    except Exception as e:  # noqa: BLE001
        logger.error(f"Anomaly training failed: {e}")
        return {"status": "failed", "error": str(e)}
"""
Training orchestrator (app/training/train_all.py).

Calls all three training pipelines in sequence:
  1. Feature engineering (applied to raw data before training)
  2. Forecast model training
  3. Anomaly detector training
  4. Waste classifier training

Called ONLY by:
  - Initial setup (seed_data.py, when no active models exist)
  - Weekly retraining schedule (scheduler.py)
  - Drift-triggered retraining (scheduler.py, when PSI > threshold)
  - Admin manual trigger (POST /api/v1/models/retrain)

NOT called by the nightly inference job.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from loguru import logger
from sqlalchemy.orm import Session

from app.features.engineering import engineer_features
from app.training.anomaly_training import train_anomaly_model
from app.training.classifier_training import train_classifier_model
from app.training.forecast_training import train_forecast_model


def run_full_training(
    db: Session,
    billing_df: pd.DataFrame,
    dataset_version: str = "manual",
) -> dict:
    """
    Runs the full training pipeline for all three models.
    Feature engineering is applied here (before training), not inside
    the individual model code, so models receive a clean feature matrix.
    """
    summary: dict = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "dataset_version": dataset_version,
        "rows": len(billing_df),
    }

    logger.info(f"Training pipeline started: {len(billing_df)} rows, version={dataset_version}")

    # Step 1 - Feature engineering (runs once, feeds all three models)
    logger.info("Step 1/4: Feature engineering")
    try:
        featured_df = engineer_features(billing_df)
        summary["feature_engineering"] = "ok"
    except Exception as e:  # noqa: BLE001
        logger.error(f"Feature engineering failed: {e}")
        summary["feature_engineering"] = f"failed: {e}"
        featured_df = billing_df  # fall back to raw features

    # Step 2 - Forecast model
    logger.info("Step 2/4: Forecast model training")
    summary["forecast"] = train_forecast_model(db, featured_df, dataset_version)

    # Step 3 - Anomaly detector
    logger.info("Step 3/4: Anomaly detector training")
    summary["anomaly"] = train_anomaly_model(db, featured_df, dataset_version)

    # Step 4 - Waste classifier
    logger.info("Step 4/4: Waste classifier training")
    summary["waste_classifier"] = train_classifier_model(db, featured_df, dataset_version)

    summary["completed_at"] = datetime.now(timezone.utc).isoformat()
    logger.info(f"Training pipeline complete: {summary}")
    return summary


def models_exist(db: Session) -> bool:
    """
    Returns True if active trained models already exist for all three
    model types. Used by the seed pipeline to decide whether to train
    or skip.
    """
    from app.db.models import ModelRegistry

    active_types = {
        row.model_type
        for row in db.query(ModelRegistry).filter(ModelRegistry.is_active.is_(True)).all()
    }
    return {"forecast", "anomaly", "waste_classifier"}.issubset(active_types)
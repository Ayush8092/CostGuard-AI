"""
Forecast training pipeline (app/training/forecast_training.py).

Separated from inference. This module is called ONLY when:
  - Initial setup (no active model exists)
  - Drift detected (PSI > threshold or MAPE degraded)
  - Weekly retraining schedule
  - Admin triggers retraining via API

It does NOT run on every nightly job.

What it does:
  Feature-engineered data -> train quantile XGBoost models ->
  evaluate against naive baseline -> save artifact (.pkl) ->
  register in model_registry -> promote to active
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from loguru import logger
from sqlalchemy.orm import Session

from app.features.engineering import engineer_features
from app.mlops.model_registry import ModelRegistryEntry, promote_model_to_active, register_model
from app.models.forecasting import HierarchicalForecaster, _build_daily_series, _make_supervised_features, _time_based_split
from app.training.model_store import cleanup_old_artifacts, save_model


def train_forecast_model(
    db: Session,
    billing_df: pd.DataFrame,
    dataset_version: str,
    services: list[str] | None = None,
) -> dict:
    """
    Trains org-total + per-service forecasters, saves artifacts, registers.
    Returns evaluation metrics for drift tracking.
    """
    if services is None:
        services = billing_df["service"].dropna().unique().tolist()

    version_tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    version = f"{dataset_version}_{version_tag}"
    metrics: dict = {}

    # Org-total forecaster
    try:
        daily = _build_daily_series(billing_df, level="org_total")
        supervised = _make_supervised_features(daily)
        train_df, test_df = _time_based_split(supervised, train_frac=0.8)

        forecaster = HierarchicalForecaster(level="org_total", service=None)
        forecaster.fit(train_df)
        evaluation = forecaster.evaluate(test_df)

        artifact_path = save_model("forecast", forecaster, version=version)

        register_model(db, ModelRegistryEntry(
            model_type="forecast",
            version=version,
            hyperparameters={"n_estimators": 150, "quantiles": [0.05, 0.5, 0.95]},
            evaluation_metrics={
                "mae": evaluation.model_metrics.mae,
                "rmse": evaluation.model_metrics.rmse,
                "mape": evaluation.model_metrics.mape,
                "naive_mape": evaluation.naive_persistence_metrics.mape,
                "error_reduction_pct": evaluation.forecast_error_reduction_pct("persistence"),
            },
            feature_set=forecaster.feature_cols,
            dataset_version=dataset_version,
            artifact_path=artifact_path,
            is_active=True,
        ))
        promote_model_to_active(db, "forecast", version)
        cleanup_old_artifacts("forecast", keep_last=3)

        metrics["org_total"] = {
            "mape": evaluation.model_metrics.mape,
            "naive_mape": evaluation.naive_persistence_metrics.mape,
            "error_reduction_pct": evaluation.forecast_error_reduction_pct("persistence"),
        }
        logger.info(f"Forecast training complete: MAPE={evaluation.model_metrics.mape:.2f}%, "
                    f"error_reduction={evaluation.forecast_error_reduction_pct('persistence'):.1f}%")

    except Exception as e:  # noqa: BLE001
        logger.error(f"Forecast org-total training failed: {e}")
        metrics["org_total"] = {"error": str(e)}

    # Per-service forecasters (saved alongside the org-total artifact)
    for service in services:
        try:
            daily_svc = _build_daily_series(billing_df, level="per_service", service=service)
            if len(daily_svc) < 30:
                continue
            supervised_svc = _make_supervised_features(daily_svc)
            train_svc, test_svc = _time_based_split(supervised_svc)
            svc_forecaster = HierarchicalForecaster(level="per_service", service=service)
            svc_forecaster.fit(train_svc)
            svc_eval = svc_forecaster.evaluate(test_svc)
            save_model(f"forecast_{service.lower()}", svc_forecaster, version=version)
            metrics[service] = {"mape": svc_eval.model_metrics.mape}
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Per-service forecast training failed for {service}: {e}")

    return {"status": "trained", "version": version, "metrics": metrics}
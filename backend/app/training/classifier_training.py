"""
Waste classifier training pipeline (app/training/classifier_training.py).

Called ONLY on initial setup, drift detection, or weekly schedule.
NOT called on every nightly job.

Wraps preprocessing + model into a sklearn Pipeline object so inference
is a clean pipeline.predict(df) call rather than separate
preprocess() -> predict() steps. The Pipeline is pickled as a single
artifact so the inference pipeline never needs to know about the
individual preprocessing steps.
"""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
from loguru import logger
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer
from sqlalchemy.orm import Session

from app.mlops.model_registry import ModelRegistryEntry, promote_model_to_active, register_model
from app.models.waste_classification import (
    RAW_FEATURE_COLS,
    WasteClassifier,
    compute_waste_score,
    train_waste_classifier,
)
from app.training.model_store import cleanup_old_artifacts, save_model


def _fill_features(X: pd.DataFrame) -> np.ndarray:
    """Fills missing values before passing to the classifier."""
    return X[RAW_FEATURE_COLS].fillna(0).values


def train_classifier_model(
    db: Session,
    billing_df: pd.DataFrame,
    dataset_version: str,
) -> dict:
    """
    Trains the waste classifier, wraps it in a sklearn Pipeline,
    saves artifact, registers in model registry, promotes to active.
    """
    version_tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    version = f"{dataset_version}_{version_tag}"

    try:
        classifier, evaluation, scored_df = train_waste_classifier(billing_df)

        # Wrap in sklearn Pipeline for clean inference:
        #   pipeline.predict(df) -> bucket labels directly
        preprocessor = FunctionTransformer(_fill_features)
        rf = classifier.model

        sklearn_pipeline = Pipeline([
            ("preprocessor", preprocessor),
            ("classifier", rf),
        ])

        # Bundle the Pipeline WITH the waste_score formula weights so
        # the inference pipeline has everything it needs in one artifact.
        artifact = {
            "pipeline": sklearn_pipeline,
            "feature_cols": RAW_FEATURE_COLS,
            "classes": list(rf.classes_),
            "evaluation": {
                "accuracy": evaluation.accuracy,
                "precision_macro": evaluation.precision_macro,
                "recall_macro": evaluation.recall_macro,
                "f1_macro": evaluation.f1_macro,
            },
        }

        artifact_path = save_model("waste_classifier", artifact, version=version)

        register_model(db, ModelRegistryEntry(
            model_type="waste_classifier",
            version=version,
            hyperparameters={"n_estimators": 200, "max_depth": 8},
            evaluation_metrics=artifact["evaluation"],
            feature_set=RAW_FEATURE_COLS,
            dataset_version=dataset_version,
            artifact_path=artifact_path,
            is_active=True,
        ))
        promote_model_to_active(db, "waste_classifier", version)
        cleanup_old_artifacts("waste_classifier", keep_last=3)

        logger.info(
            f"Classifier training complete: accuracy={evaluation.accuracy:.4f}, "
            f"f1_macro={evaluation.f1_macro:.4f}"
        )
        return {
            "status": "trained",
            "version": version,
            "artifact_path": artifact_path,
            "metrics": artifact["evaluation"],
        }

    except Exception as e:  # noqa: BLE001
        logger.error(f"Classifier training failed: {e}")
        return {"status": "failed", "error": str(e)}
"""
Model persistence (app/training/model_store.py).

Saves and loads trained model artifacts (.pkl files) to/from disk.
This is separate from the model_registry table in Postgres, which only
holds metadata (version, metrics, hyperparameters). The registry points
to the artifact path on disk; this module handles the actual bytes.

Directory layout:
  /app/data/model_artifacts/
    forecast/
      forecast_v20240101.pkl
      forecast_v20240108.pkl   <- ACTIVE (symlink or registry flag)
    waste_classifier/
      waste_classifier_v20240101.pkl
    anomaly/
      anomaly_v20240101.pkl
"""
from __future__ import annotations

import os
import pickle
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

ARTIFACT_BASE_DIR = os.environ.get("MODEL_ARTIFACT_DIR", "/app/data/model_artifacts")


def _artifact_dir(model_type: str) -> str:
    d = os.path.join(ARTIFACT_BASE_DIR, model_type)
    os.makedirs(d, exist_ok=True)
    return d


def _version_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def save_model(model_type: str, model_object, version: str | None = None) -> str:
    """
    Serialises model_object to a versioned .pkl file.
    Returns the full path to the saved artifact.
    """
    version = version or _version_tag()
    artifact_dir = _artifact_dir(model_type)
    filename = f"{model_type}_{version}.pkl"
    path = os.path.join(artifact_dir, filename)
    with open(path, "wb") as f:
        pickle.dump(model_object, f, protocol=pickle.HIGHEST_PROTOCOL)
    logger.info(f"Saved {model_type} artifact: {path}")
    return path


def load_model(artifact_path: str):
    """
    Loads a model artifact from the given path.
    Raises FileNotFoundError if the artifact does not exist.
    """
    if not os.path.exists(artifact_path):
        raise FileNotFoundError(
            f"Model artifact not found: {artifact_path}. "
            "Run the training pipeline first, or trigger a manual retrain."
        )
    with open(artifact_path, "rb") as f:
        model = pickle.load(f)
    logger.info(f"Loaded artifact from {artifact_path}")
    return model


def load_active_model(model_type: str, db):
    """
    Convenience function: looks up the active model version in the
    model_registry table, then loads and returns the artifact from disk.

    This is the function called by the nightly inference pipeline:
        forecaster = load_active_model("forecast", db)
        forecaster.predict(X)
    """
    from app.db.models import ModelRegistry

    active = db.query(ModelRegistry).filter(
        ModelRegistry.model_type == model_type,
        ModelRegistry.is_active.is_(True),
    ).first()

    if active is None:
        raise RuntimeError(
            f"No active model registered for type '{model_type}'. "
            "Run the training pipeline first."
        )
    if not active.artifact_path:
        raise RuntimeError(
            f"Active model '{model_type}' v{active.version} has no artifact_path "
            "in the registry. Was the training pipeline interrupted?"
        )
    return load_model(active.artifact_path)


def list_artifacts(model_type: str) -> list[str]:
    """Returns all saved artifact paths for a model type, newest first."""
    d = _artifact_dir(model_type)
    paths = sorted(Path(d).glob(f"{model_type}_*.pkl"), reverse=True)
    return [str(p) for p in paths]


def cleanup_old_artifacts(model_type: str, keep_last: int = 3) -> int:
    """Deletes old artifact files, keeping the most recent `keep_last`."""
    paths = list_artifacts(model_type)
    to_delete = paths[keep_last:]
    for p in to_delete:
        os.remove(p)
        logger.info(f"Deleted old artifact: {p}")
    return len(to_delete)
"""
Model Monitoring route (Part 9, Tab 9). Surfaces drift status, retraining
policy decisions, the model registry table, and a load-test summary
read from a static results file (Part 8 load-test deliverable).
"""
from __future__ import annotations

import json
import os

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, require_role
from app.db.models import ModelRegistry
from app.db.session import get_db
from app.mlops.model_registry import registry_entry_to_dict

router = APIRouter(prefix="/models", tags=["model_monitoring"])

LOAD_TEST_RESULTS_PATH = os.environ.get("LOAD_TEST_RESULTS_PATH", "/app/data/load_test_results.json")


class ModelRegistryOut(BaseModel):
    model_config = {"protected_namespaces": ()}  # "model_type" below is a legitimate field name, not a Pydantic internal

    id: str
    model_type: str
    version: str
    training_date: str | None
    hyperparameters: dict | None
    evaluation_metrics: dict | None
    feature_set: list | None
    dataset_version: str | None
    is_active: bool


@router.get("/registry", response_model=list[ModelRegistryOut])
def get_model_registry(
    model_type: str | None = None,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ModelRegistryOut]:
    # Model registry is global (not org-scoped) - models are trained once
    # across the platform's reference datasets, not per-tenant.
    query = db.query(ModelRegistry).order_by(ModelRegistry.training_date.desc())
    if model_type:
        query = query.filter(ModelRegistry.model_type == model_type)
    rows = query.all()
    return [ModelRegistryOut(**registry_entry_to_dict(r)) for r in rows]


@router.get("/load-test-summary")
def get_load_test_summary(current_user: CurrentUser = Depends(get_current_user)) -> dict:
    if not os.path.exists(LOAD_TEST_RESULTS_PATH):
        return {"available": False, "note": "Load test has not been run yet. See docs/LOAD_TESTING.md."}
    with open(LOAD_TEST_RESULTS_PATH) as f:
        return {"available": True, **json.load(f)}


@router.post("/retrain")
def trigger_manual_retrain(current_user: CurrentUser = Depends(require_role("admin"))) -> dict:
    """
    Manual trigger via API (Part 6 retraining policy condition). Runs the
    same nightly job pipeline synchronously for immediate feedback -
    admin-only since this is a meaningfully expensive operation across
    every organization.
    """
    from app.workers.scheduler import trigger_nightly_job_now

    trigger_nightly_job_now()
    return {"triggered": True, "triggered_by": current_user.email}

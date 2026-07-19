"""
Nightly job orchestrator (Part 8) - THIN ORCHESTRATOR ONLY.

This module no longer trains models. It is a thin wrapper that:
  1. Checks whether active trained models exist
  2. If YES  -> calls the inference pipeline (nightly_inference.py)
  3. If NO   -> calls the training pipeline first, then inference

Training happens in app/training/train_all.py.
Inference happens in app/workers/nightly_inference.py.

This separation means:
  - The nightly job runs inference only on 99% of nights (fast, cheap)
  - Training only runs when actually needed (first run, drift, weekly)
  - Each concern lives in one place and can be tested independently

Run modes:
  - Scheduled: APScheduler triggers run_nightly_job_all_orgs() nightly
  - Manual:    python -m app.workers.nightly_job --org-id <id>
"""
from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.orm import Session

from app.db.models import Organization
from app.db.session import SessionLocal


def _load_org_billing_df(db: Session, org_id: str):
    """Loads billing data for one org from processed_telemetry."""
    import pandas as pd
    from app.db.models import ProcessedTelemetry

    rows = db.query(ProcessedTelemetry).filter(
        ProcessedTelemetry.organization_id == org_id
    ).all()
    return pd.DataFrame([{
        "date": r.date, "account_id": r.account_id, "service": r.service,
        "resource_id": r.resource_id, "instance_type": r.instance_type,
        "region": r.region, "cost": r.cost, "usage_hours": r.usage_hours,
        "cpu_avg_pct": r.cpu_avg_pct, "memory_avg_pct": r.memory_avg_pct,
        "disk_io": r.disk_io, "network_io": r.network_io,
        "runtime_days": r.runtime_days, "cost_growth_rate": r.cost_growth_rate,
        "anomaly_history_count": r.anomaly_history_count,
    } for r in rows])


def run_nightly_job_for_org(db: Session, org_id: str, dataset_version: str = "nightly") -> dict:
    """
    Orchestrates the nightly pipeline for ONE org:
      1. Load data
      2. If no active models exist -> train first
      3. Run inference using active models
      4. Results written to DB by nightly_inference.py
    """
    summary: dict = {
        "org_id": org_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }

    billing_df = _load_org_billing_df(db, org_id)
    if billing_df.empty or len(billing_df) < 30:
        logger.warning(f"org {org_id}: insufficient data ({len(billing_df)} rows), skipping")
        return {"org_id": org_id, "status": "skipped", "reason": "insufficient_data"}

    # Check if active models exist - train first if not
    from app.training.train_all import models_exist, run_full_training
    if not models_exist(db):
        logger.info(f"org {org_id}: no active models found - running initial training")
        train_result = run_full_training(db, billing_df, dataset_version=dataset_version)
        summary["training"] = train_result
        logger.info(f"org {org_id}: initial training complete")
    else:
        summary["training"] = "skipped_active_models_exist"

    # Run inference using the now-confirmed active models
    from app.workers.nightly_inference import run_inference_for_org
    inference_result = run_inference_for_org(db, org_id)
    summary["inference"] = inference_result
    summary["status"] = inference_result.get("status", "ok")
    summary["completed_at"] = datetime.now(timezone.utc).isoformat()

    return summary


def run_nightly_job_all_orgs() -> list[dict]:
    """Entry point called by the scheduler every night."""
    db = SessionLocal()
    try:
        org_ids = [o.id for o in db.query(Organization).all()]
        results = []
        for org_id in org_ids:
            logger.info(f"Nightly job starting for org {org_id}")
            results.append(run_nightly_job_for_org(db, org_id))
        return results
    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--org-id", required=False)
    args = parser.parse_args()

    if args.org_id:
        db = SessionLocal()
        try:
            print(run_nightly_job_for_org(db, args.org_id))
        finally:
            db.close()
    else:
        for result in run_nightly_job_all_orgs():
            print(result)
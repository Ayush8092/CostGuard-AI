"""
APScheduler wiring (Part 8).

Schedule:
  Every night at NIGHTLY_JOB_HOUR UTC -> inference only (fast, cheap)
  Every Sunday at 03:00 UTC           -> drift check -> retrain if needed

Training is NOT part of the nightly schedule. The nightly job calls
nightly_inference.py which loads active .pkl artifacts and predicts.
Retraining only runs when:
  - No active models exist (first run, handled inside nightly_job.py)
  - Drift detected (PSI > threshold, handled by weekly job below)
  - Weekly Sunday schedule
  - Admin manual trigger via POST /api/v1/models/retrain
"""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from app.core.config import get_settings

_scheduler: BackgroundScheduler | None = None


def _safe_run(task_name: str, fn, *args, **kwargs) -> None:
    """Wraps any scheduled task so a failure never kills the scheduler thread."""
    try:
        logger.info(f"Scheduled task starting: {task_name}")
        result = fn(*args, **kwargs)
        logger.info(f"Scheduled task complete: {task_name} -> {result}")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Scheduled task FAILED: {task_name} -> {e}")


def _run_nightly_inference() -> list[dict]:
    """
    Nightly task: inference only.
    Loads active trained models, runs predictions, stores results, 
    invalidates Redis cache. Does NOT retrain.
    """
    from app.workers.nightly_job import run_nightly_job_all_orgs
    return run_nightly_job_all_orgs()


def _run_weekly_drift_check_and_retrain() -> dict:
    """
    Weekly task: checks PSI/KS drift across all orgs.
    Only retrains if drift is detected or 7 days have elapsed since
    last training. Never retrains just because it's Sunday if nothing
    has drifted and a recent model exists.
    """
    import pandas as pd
    from app.db.session import SessionLocal
    from app.db.models import Organization, ProcessedTelemetry
    from app.mlops.drift_detection import compute_drift_report, evaluate_retraining_policy

    db = SessionLocal()
    summary: dict = {}

    try:
        org_ids = [o.id for o in db.query(Organization).all()]

        for org_id in org_ids:
            rows = db.query(ProcessedTelemetry).filter(
                ProcessedTelemetry.organization_id == org_id
            ).all()

            if len(rows) < 60:
                summary[org_id] = "skipped_insufficient_data"
                continue

            df = pd.DataFrame([{
                "cost": r.cost,
                "cpu_avg_pct": r.cpu_avg_pct,
                "memory_avg_pct": r.memory_avg_pct,
                "date": r.date,
            } for r in rows]).sort_values("date").reset_index(drop=True)

            split = int(len(df) * 0.8)
            train_df, new_df = df.iloc[:split], df.iloc[split:]

            drift_results = compute_drift_report(
                train_df, new_df,
                features=["cost", "cpu_avg_pct", "memory_avg_pct"],
            )

            decision = evaluate_retraining_policy(
                drift_results,
                days_since_last_training=7,
            )

            if decision.should_retrain:
                logger.info(f"Drift/schedule triggered retraining for org {org_id}: {decision.reasons}")
                from app.workers.nightly_job import _load_org_billing_df
                from app.training.train_all import run_full_training
                billing_df = _load_org_billing_df(db, org_id)
                train_result = run_full_training(db, billing_df, dataset_version="weekly_retrain")
                summary[org_id] = {"retrained": True, "reasons": decision.reasons, "result": train_result}
            else:
                summary[org_id] = {"retrained": False, "reason": "no_drift_detected"}

    finally:
        db.close()

    return summary


def trigger_nightly_job_now() -> None:
    """Manual trigger via API. Admin-only. Runs inference (or training if no models exist)."""
    _safe_run("manual_trigger_nightly", _run_nightly_inference)


def trigger_post_upload(org_id: str) -> None:
    """Called after a CSV upload finishes - runs the pipeline for this org immediately."""
    import threading

    def _run():
        from app.db.session import SessionLocal
        from app.workers.nightly_job import run_nightly_job_for_org
        db = SessionLocal()
        try:
            _safe_run(f"post_upload_pipeline org={org_id}", run_nightly_job_for_org, db, org_id, "csv_upload")
        finally:
            db.close()

    threading.Thread(target=_run, daemon=True).start()


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    settings = get_settings()
    scheduler = BackgroundScheduler(timezone="UTC")

    # Nightly: inference only (runs every night at NIGHTLY_JOB_HOUR UTC)
    scheduler.add_job(
        lambda: _safe_run("nightly_inference", _run_nightly_inference),
        trigger=CronTrigger(hour=settings.NIGHTLY_JOB_HOUR, minute=0),
        id="nightly_inference",
        replace_existing=True,
    )

    # Weekly: drift check + conditional retraining (every Sunday at 03:00 UTC)
    scheduler.add_job(
        lambda: _safe_run("weekly_drift_retrain", _run_weekly_drift_check_and_retrain),
        trigger=CronTrigger(day_of_week="sun", hour=3, minute=0),
        id="weekly_drift_retrain",
        replace_existing=True,
    )

    scheduler.start()
    _scheduler = scheduler
    logger.info(
        f"Scheduler started: nightly inference at {settings.NIGHTLY_JOB_HOUR}:00 UTC daily, "
        f"weekly drift+retrain on Sundays at 03:00 UTC"
    )
    return scheduler
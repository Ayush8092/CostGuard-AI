"""
Nightly inference pipeline (app/workers/nightly_inference.py).

This is what runs EVERY NIGHT. It does NOT train any model.
The architecture is exactly as described in the production spec:

  Load active models (from .pkl artifacts on disk)
        |
        v
  Run inference on new data
        |
        v
  Forecast + Anomaly scores + Waste classification
        |
        v
  SHAP explainability
        |
        v
  LLM recommendation generation (skips if recs already exist)
        |
        v
  Save to PostgreSQL
        |
        v
  Invalidate Redis cache (so next request loads fresh data)
        |
        v
  Dashboard / FastAPI reads from DB

Training is handled separately by app/training/train_all.py and is
triggered by the weekly schedule or drift detection, not this module.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from loguru import logger
from sqlalchemy.orm import Session

from app.db.models import (
    Anomaly,
    ForecastResult,
    IncidentScore,
    Organization,
    ProcessedTelemetry,
    Recommendation,
    WasteClassification,
)
from app.db.session import SessionLocal
from app.models.anomaly_detection import (
    DIMENSIONS,
    SEVERITY_BANDS,
    _add_resource_relative_features,
    _normalize_anomaly_scores,
)
from app.models.forecasting import (
    _build_daily_series,
    _make_supervised_features,
    _time_based_split,
)
from app.models.waste_classification import compute_waste_score, _bucket_for_score
from app.training.model_store import load_active_model


def _load_org_billing_df(db: Session, org_id: str) -> pd.DataFrame:
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


def _invalidate_cache(org_id: str) -> None:
    """
    Deletes the org's cached dashboard entry from Redis so the next
    request loads fresh data from Postgres rather than stale cache.
    This is correct cache invalidation - delete then let the next
    request repopulate - NOT a cache refresh that pushes stale data.
    """
    try:
        from app.core.cache import get_redis_client
        redis = get_redis_client()
        cache_key = f"dashboard:{org_id}"
        redis.delete(cache_key)
        logger.info(f"Cache invalidated for org {org_id}")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Cache invalidation failed for org {org_id}: {e}")


def run_forecast_inference(
    db: Session,
    org_id: str,
    billing_df: pd.DataFrame,
    dataset_version: str,
) -> int:
    """Loads active forecast model, generates predictions, saves to DB."""
    rows_written = 0
    try:
        forecaster = load_active_model("forecast", db)
        services = billing_df["service"].dropna().unique().tolist()

        # Org-total
        daily = _build_daily_series(billing_df, level="org_total")
        supervised = _make_supervised_features(daily)
        _, test_df = _time_based_split(supervised, train_frac=0.8)
        preds = forecaster.predict(test_df)
        latest = preds.iloc[-1]
        db.add(ForecastResult(
            id=str(uuid.uuid4()), organization_id=org_id,
            level="org_total", service=None,
            forecast_date=test_df["date"].iloc[-1],
            forecast=float(latest["forecast"]),
            ci_lower=float(latest["ci_lower"]),
            ci_upper=float(latest["ci_upper"]),
            naive_baseline=float(test_df["lag_1d"].iloc[-1]) if pd.notna(test_df["lag_1d"].iloc[-1]) else None,
            model_version=dataset_version,
        ))
        rows_written += 1

        # Per-service (best-effort, skip if per-service artifact not saved)
        for service in services:
            try:
                from app.training.model_store import load_model, _artifact_dir
                import os
                svc_dir = _artifact_dir(f"forecast_{service.lower()}")
                pkls = sorted(os.listdir(svc_dir))
                if not pkls:
                    continue
                svc_forecaster = load_model(os.path.join(svc_dir, pkls[-1]))
                daily_svc = _build_daily_series(billing_df, level="per_service", service=service)
                if len(daily_svc) < 10:
                    continue
                supervised_svc = _make_supervised_features(daily_svc)
                _, test_svc = _time_based_split(supervised_svc)
                svc_preds = svc_forecaster.predict(test_svc)
                svc_latest = svc_preds.iloc[-1]
                db.add(ForecastResult(
                    id=str(uuid.uuid4()), organization_id=org_id,
                    level="per_service", service=service,
                    forecast_date=test_svc["date"].iloc[-1],
                    forecast=float(svc_latest["forecast"]),
                    ci_lower=float(svc_latest["ci_lower"]),
                    ci_upper=float(svc_latest["ci_upper"]),
                    naive_baseline=float(test_svc["lag_1d"].iloc[-1]) if pd.notna(test_svc["lag_1d"].iloc[-1]) else None,
                    model_version=dataset_version,
                ))
                rows_written += 1
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Per-service forecast inference failed for {service}: {e}")

    except Exception as e:  # noqa: BLE001
        logger.error(f"Forecast inference failed for org {org_id}: {e}")

    return rows_written


def run_anomaly_inference(
    db: Session,
    org_id: str,
    billing_df: pd.DataFrame,
    dataset_version: str,
) -> int:
    """Loads active anomaly artifact, scores all rows, saves to DB."""
    rows_written = 0
    try:
        artifact = load_active_model("anomaly", db)
        dimension_models = artifact["dimension_models"]
        dimensions_used = artifact["dimensions_used"]

        featured_df = _add_resource_relative_features(billing_df, DIMENSIONS)
        out = featured_df.copy()

        for dim, model in dimension_models.items():
            z_col = f"{dim}_resource_zscore"
            feature_cols = [dim] + ([z_col] if z_col in out.columns else [])
            mask = out[feature_cols].notna().all(axis=1)
            scores = np.full(len(out), np.nan)
            if mask.sum() > 0:
                raw = model.score_samples(out.loc[mask, feature_cols])
                scores[mask.values] = _normalize_anomaly_scores(raw)
            out[f"anomaly_score_{dim}"] = scores

        # Compute weighted incident_score
        weights = artifact["incident_score_weights"]
        weight_sum = sum(weights.get(d, 0) for d in dimensions_used)
        incident_score = np.zeros(len(out))
        for dim in dimensions_used:
            col = f"anomaly_score_{dim}"
            w = weights.get(dim, 0) / max(weight_sum, 1e-9)
            incident_score += np.nan_to_num(out[col].values, nan=0.0) * w
        out["incident_score"] = np.round(incident_score, 2)

        def _severity(score: float) -> str:
            for threshold, label in artifact["severity_bands"]:
                if score >= threshold:
                    return label
            return "low"

        out["severity"] = out["incident_score"].apply(_severity)

        # Save only the most recent date's anomaly scores to avoid
        # growing the anomalies table unboundedly with repeated daily runs
        latest_date = pd.to_datetime(billing_df["date"]).max()
        recent = out[pd.to_datetime(out["date"]) == latest_date]

        for _, row in recent.iterrows():
            dim_scores = {dim: row.get(f"anomaly_score_{dim}") for dim in dimensions_used}
            db.add(Anomaly(
                id=str(uuid.uuid4()),
                organization_id=org_id,
                resource_id=str(row["resource_id"]),
                date=row["date"],
                dimension_scores={k: (None if pd.isna(v) else round(float(v), 2))
                                   for k, v in dim_scores.items()},
                incident_score=float(row["incident_score"]),
                severity=row["severity"],
                is_ground_truth_eval=False,
                model_version=dataset_version,
            ))
            rows_written += 1

        avg_incident = float(recent["incident_score"].mean()) if len(recent) else 0.0
        high_count = int((recent["severity"].isin(["high", "critical"])).sum())
        db.add(IncidentScore(
            id=str(uuid.uuid4()), organization_id=org_id, date=latest_date,
            avg_incident_score=round(avg_incident, 2), high_severity_count=high_count,
        ))

    except Exception as e:  # noqa: BLE001
        logger.error(f"Anomaly inference failed for org {org_id}: {e}")

    return rows_written


def run_waste_inference(
    db: Session,
    org_id: str,
    billing_df: pd.DataFrame,
    dataset_version: str,
) -> tuple[int, pd.DataFrame]:
    """
    Loads active waste classifier artifact (sklearn Pipeline), scores
    all resources, computes SHAP values, saves to DB.
    Returns (rows_written, waste_scored_latest_df).
    """
    rows_written = 0
    waste_scored_latest = pd.DataFrame()

    try:
        artifact = load_active_model("waste_classifier", db)
        pipeline = artifact["pipeline"]
        feature_cols = artifact["feature_cols"]

        # Compute waste_score via formula (scoring function, not the model)
        waste_score_series, _ = compute_waste_score(billing_df)
        out = billing_df.copy()
        out["waste_score"] = waste_score_series
        out["bucket"] = waste_score_series.apply(_bucket_for_score)

        # Classifier prediction via Pipeline (clean: pipeline.predict(df))
        X = out[feature_cols].fillna(0)
        out["predicted_bucket"] = pipeline.predict(X)

        latest_date = pd.to_datetime(out["date"]).max()
        waste_scored_latest = out[pd.to_datetime(out["date"]) == latest_date].copy()

        # SHAP: computed immediately after inference, stored in DB, never on user request
        from app.models.explainability import explain_waste_prediction
        from app.models.waste_classification import WasteClassifier as WCls

        # Reconstruct a WasteClassifier wrapper around the saved RF so
        # SHAP's TreeExplainer can access .classes_ and .feature_cols
        wc_wrapper = WCls()
        wc_wrapper.model = pipeline.named_steps["classifier"]
        wc_wrapper.feature_cols = feature_cols
        wc_wrapper.classes_ = artifact["classes"]

        for _, row in waste_scored_latest.iterrows():
            shap_top = None
            try:
                row_df = pd.DataFrame([{col: row.get(col, 0) for col in feature_cols}])
                waste_explanations = explain_waste_prediction(wc_wrapper, row_df, top_n=5)
                bucket = row.get("bucket", "")
                if bucket in waste_explanations:
                    shap_top = {c.feature: round(c.shap_value, 4)
                                for c in waste_explanations[bucket].top_contributions[:5]}
            except Exception:  # noqa: BLE001
                shap_top = None

            db.add(WasteClassification(
                id=str(uuid.uuid4()),
                organization_id=org_id,
                resource_id=str(row["resource_id"]),
                date=row["date"],
                waste_score=float(row["waste_score"]),
                bucket=row["bucket"],
                predicted_bucket=row.get("predicted_bucket"),
                shap_top_features=shap_top,
                model_version=dataset_version,
            ))
            rows_written += 1

    except Exception as e:  # noqa: BLE001
        logger.error(f"Waste inference failed for org {org_id}: {e}")

    return rows_written, waste_scored_latest


def run_recommendation_inference(
    db: Session,
    org_id: str,
    waste_scored_latest: pd.DataFrame,
) -> int:
    """
    Generates LLM recommendations. SKIPS any resource that already has
    an open recommendation to avoid wasting free-tier LLM tokens.
    """
    rows_written = 0
    if waste_scored_latest.empty:
        return 0

    try:
        # Point 8: skip if recommendation already exists for this resource
        existing_recs = {
            r.resource_id for r in db.query(Recommendation).filter(
                Recommendation.organization_id == org_id,
                Recommendation.status == "open",
            ).all()
        }

        needs_rec = waste_scored_latest[
            ~waste_scored_latest["resource_id"].isin(existing_recs)
        ]

        if needs_rec.empty:
            logger.info(f"org {org_id}: all waste resources already have open recommendations, skipping LLM")
            return 0

        from app.llm.advisor import generate_recommendations
        from app.rag.faiss_store import get_knowledge_base

        kb = None
        try:
            kb = get_knowledge_base()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"FAISS knowledge base unavailable: {e}")

        recs = generate_recommendations(needs_rec, knowledge_base=kb)
        for r in recs:
            db.add(Recommendation(
                id=str(uuid.uuid4()),
                organization_id=org_id,
                resource_id=r.resource_id,
                action=r.action,
                estimated_savings=r.estimated_savings,
                confidence=r.confidence,
                reason=r.reason,
                supporting_rule=r.supporting_rule,
                impact_tier=r.impact_tier,
                impact_score=r.impact_score,
                citation_chunk_ids=[r.supporting_chunk_id] if r.supporting_chunk_id else [],
                status="open",
            ))
            rows_written += 1

    except Exception as e:  # noqa: BLE001
        logger.error(f"Recommendation inference failed for org {org_id}: {e}")

    return rows_written


def run_inference_for_org(db: Session, org_id: str) -> dict:
    """
    Full inference pipeline for one organization:
      load data -> forecast -> anomaly -> waste+SHAP -> recommendations
                -> save to DB -> invalidate cache

    This is the function the nightly scheduler calls every day.
    It NEVER trains. It ONLY predicts using already-trained active models.
    """
    billing_df = _load_org_billing_df(db, org_id)
    if billing_df.empty or len(billing_df) < 30:
        logger.warning(f"org {org_id}: insufficient data ({len(billing_df)} rows), skipping inference")
        return {"org_id": org_id, "status": "skipped", "reason": "insufficient_data"}

    dataset_version = f"inference_{datetime.now(timezone.utc).strftime('%Y%m%d')}"
    summary: dict = {"org_id": org_id, "status": "ok", "dataset_version": dataset_version}

    from app.features.engineering import engineer_features
    try:
        billing_df = engineer_features(billing_df)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Feature engineering failed for org {org_id}, using raw features: {e}")

    # Run each inference stage independently so one failure doesn't block the rest
    summary["forecast_rows"] = run_forecast_inference(db, org_id, billing_df, dataset_version)
    summary["anomaly_rows"] = run_anomaly_inference(db, org_id, billing_df, dataset_version)
    waste_rows, waste_scored = run_waste_inference(db, org_id, billing_df, dataset_version)
    summary["waste_rows"] = waste_rows
    summary["recommendation_rows"] = run_recommendation_inference(db, org_id, waste_scored)

    db.commit()

    # Invalidate Redis cache so next dashboard request loads fresh data
    _invalidate_cache(org_id)

    summary["completed_at"] = datetime.now(timezone.utc).isoformat()
    return summary


def run_inference_all_orgs() -> list[dict]:
    db = SessionLocal()
    try:
        org_ids = [o.id for o in db.query(Organization).all()]
        results = []
        for org_id in org_ids:
            logger.info(f"Running inference for org {org_id}")
            results.append(run_inference_for_org(db, org_id))
        return results
    finally:
        db.close()
"""
Business metrics route — exposes the requested resume/dashboard KPIs.
All DB queries are wrapped in try/except so a missing column or empty
table returns a sensible default instead of a 500.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.db.models import (
    Anomaly, ProcessedTelemetry, Recommendation,
    WasteClassification,
)
from app.db.session import get_db

router = APIRouter(prefix="/business-metrics", tags=["business_metrics"])


class BusinessMetrics(BaseModel):
    estimated_monthly_savings: float
    waste_detection_coverage_pct: float
    forecast_error_reduction_pct: float | None
    optimization_opportunity_rate_pct: float
    avg_recommendation_confidence_pct: float
    idle_resource_reduction_potential_pct: float | None
    infrastructure_health_score: float | None


@router.get("", response_model=BusinessMetrics)
def get_business_metrics(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BusinessMetrics:
    org = current_user.organization_id

    # ── Estimated monthly savings ─────────────────────────────────────────
    try:
        savings = db.query(
            func.coalesce(func.sum(Recommendation.estimated_savings), 0.0)
        ).filter(
            Recommendation.organization_id == org,
            Recommendation.status == "open",
        ).scalar() or 0.0
    except Exception:
        savings = 0.0

    # ── Waste detection coverage ──────────────────────────────────────────
    try:
        total_waste = db.query(func.count(WasteClassification.id)).filter(
            WasteClassification.organization_id == org,
            WasteClassification.bucket.in_(["Idle", "Critical Waste", "Underutilized"]),
        ).scalar() or 0

        waste_with_rec = db.query(
            func.count(func.distinct(Recommendation.resource_id))
        ).filter(
            Recommendation.organization_id == org,
            Recommendation.status == "open",
        ).scalar() or 0

        coverage = (waste_with_rec / total_waste * 100) if total_waste > 0 else 0.0
    except Exception:
        coverage = 0.0

    # ── Forecast error reduction — read from model registry safely ────────
    forecast_error_reduction: float | None = None
    try:
        from app.db.models import ModelRegistry
        from sqlalchemy import text

        # Use raw SQL so we never reference a column that might not exist
        row = db.execute(text(
            "SELECT evaluation_metrics FROM model_registry "
            "WHERE model_type = 'forecast' AND is_active = true "
            "ORDER BY training_date DESC LIMIT 1"
        )).fetchone()

        if row and row[0]:
            metrics = row[0]
            if isinstance(metrics, dict) and "error_reduction_pct" in metrics:
                forecast_error_reduction = float(metrics["error_reduction_pct"])
    except Exception:
        forecast_error_reduction = None

    # ── Optimization opportunity rate ─────────────────────────────────────
    try:
        total_resources = db.query(
            func.count(func.distinct(ProcessedTelemetry.resource_id))
        ).filter(
            ProcessedTelemetry.organization_id == org,
        ).scalar() or 0

        needing_opt = db.query(
            func.count(func.distinct(WasteClassification.resource_id))
        ).filter(
            WasteClassification.organization_id == org,
            WasteClassification.bucket.in_(["Idle", "Critical Waste", "Underutilized"]),
        ).scalar() or 0

        opp_rate = (needing_opt / total_resources * 100) if total_resources > 0 else 0.0
    except Exception:
        opp_rate = 0.0

    # ── Average recommendation confidence ─────────────────────────────────
    try:
        avg_conf = db.query(
            func.coalesce(func.avg(Recommendation.confidence), 0.0)
        ).filter(
            Recommendation.organization_id == org,
            Recommendation.status == "open",
        ).scalar() or 0.0
        avg_conf_pct = float(avg_conf) * 100 if float(avg_conf) <= 1.0 else float(avg_conf)
    except Exception:
        avg_conf_pct = 0.0

    # ── Idle resource reduction potential ─────────────────────────────────
    idle_reduction: float | None = None
    try:
        idle_total = db.query(func.count(WasteClassification.id)).filter(
            WasteClassification.organization_id == org,
            WasteClassification.bucket.in_(["Idle", "Critical Waste"]),
        ).scalar() or 0

        recommended_for_termination = db.query(
            func.count(func.distinct(Recommendation.resource_id))
        ).filter(
            Recommendation.organization_id == org,
            Recommendation.status == "open",
            Recommendation.action.ilike("%terminat%"),
        ).scalar() or 0

        if idle_total > 0:
            idle_reduction = round(recommended_for_termination / idle_total * 100, 1)
    except Exception:
        idle_reduction = None

    # ── Infrastructure health score ───────────────────────────────────────
    health_score: float | None = None
    try:
        anomaly_count = db.query(func.count(Anomaly.id)).filter(
            Anomaly.organization_id == org,
        ).scalar() or 0

        waste_ratio = (needing_opt / max(total_resources, 1)) if total_resources else 0.0
        anomaly_norm = min(anomaly_count / 50.0, 1.0)  # cap at 50 anomalies
        risk = (0.5 * waste_ratio + 0.5 * anomaly_norm)
        health_score = round((1.0 - risk) * 100, 1)
    except Exception:
        health_score = None

    return BusinessMetrics(
        estimated_monthly_savings=round(float(savings), 2),
        waste_detection_coverage_pct=round(float(coverage), 1),
        forecast_error_reduction_pct=round(forecast_error_reduction, 1) if forecast_error_reduction is not None else None,
        optimization_opportunity_rate_pct=round(float(opp_rate), 1),
        avg_recommendation_confidence_pct=round(float(avg_conf_pct), 1),
        idle_resource_reduction_potential_pct=idle_reduction,
        infrastructure_health_score=health_score,
    )

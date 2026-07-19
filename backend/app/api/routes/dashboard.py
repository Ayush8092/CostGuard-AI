"""
Dashboard route - reads KPIs from Redis cache, falls back to Postgres.
Uses safe redis_get/redis_set helpers so Redis failure = cache miss, never a crash.
"""
from __future__ import annotations
import json
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.api.deps import CurrentUser, get_current_user
from app.core.cache import redis_get, redis_set
from app.core.config import get_settings
from app.db.models import Anomaly, ForecastResult, ProcessedTelemetry, Recommendation
from app.db.session import get_db

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
CACHE_KEY_TEMPLATE = "dashboard:{org_id}"


class DashboardKpis(BaseModel):
    total_spend_30d: float
    forecast_next_period: float | None
    anomaly_count_30d: int
    savings_identified: float
    active_resource_count: int


def _build_kpis_from_db(db: Session, org_id: str) -> DashboardKpis:
    total_spend = db.query(func.coalesce(func.sum(ProcessedTelemetry.cost), 0.0)).filter(
        ProcessedTelemetry.organization_id == org_id).scalar()
    active_resources = db.query(func.count(func.distinct(ProcessedTelemetry.resource_id))).filter(
        ProcessedTelemetry.organization_id == org_id).scalar()
    anomaly_count = db.query(func.count(Anomaly.id)).filter(
        Anomaly.organization_id == org_id).scalar()
    latest_forecast = db.query(ForecastResult).filter(
        ForecastResult.organization_id == org_id,
        ForecastResult.level == "org_total",
    ).order_by(ForecastResult.forecast_date.desc()).first()
    total_savings = db.query(func.coalesce(func.sum(Recommendation.estimated_savings), 0.0)).filter(
        Recommendation.organization_id == org_id,
        Recommendation.status == "open").scalar()
    return DashboardKpis(
        total_spend_30d=round(float(total_spend or 0), 2),
        forecast_next_period=round(float(latest_forecast.forecast), 2) if latest_forecast else None,
        anomaly_count_30d=int(anomaly_count or 0),
        savings_identified=round(float(total_savings or 0), 2),
        active_resource_count=int(active_resources or 0),
    )


@router.get("", response_model=DashboardKpis)
def get_dashboard(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DashboardKpis:
    settings = get_settings()
    org_id = current_user.organization_id
    cache_key = CACHE_KEY_TEMPLATE.format(org_id=org_id)

    # Try Redis cache first — redis_get returns None on any failure
    cached = redis_get(cache_key)
    if cached:
        try:
            return DashboardKpis(**json.loads(cached))
        except Exception:
            pass  # corrupted cache entry — rebuild from DB

    # Build from Postgres
    result = _build_kpis_from_db(db, org_id)

    # Write back to cache — redis_set silently ignores failures
    redis_set(cache_key, json.dumps(result.model_dump()), settings.REDIS_TTL_SECONDS)

    return result

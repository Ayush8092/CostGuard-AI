"""
Forecasting route (Part 9, Tab 2). Reads cached forecast_results rows -
forecasts are computed by the nightly job (Part 8), never on request.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.db.models import ForecastResult
from app.db.session import get_db

router = APIRouter(prefix="/forecast", tags=["forecasting"])


class ForecastPoint(BaseModel):
    forecast_date: str
    forecast: float
    ci_lower: float
    ci_upper: float
    naive_baseline: float | None
    service: str | None


@router.get("", response_model=list[ForecastPoint])
def get_forecast(
    level: str = Query("org_total", pattern="^(org_total|per_service)$"),
    service: str | None = Query(None),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ForecastPoint]:
    query = db.query(ForecastResult).filter(
        ForecastResult.organization_id == current_user.organization_id,
        ForecastResult.level == level,
    )
    if service:
        query = query.filter(ForecastResult.service == service)

    rows = query.order_by(ForecastResult.forecast_date.asc()).all()
    return [
        ForecastPoint(
            forecast_date=r.forecast_date.isoformat(),
            forecast=round(r.forecast, 2),
            ci_lower=round(r.ci_lower, 2),
            ci_upper=round(r.ci_upper, 2),
            naive_baseline=round(r.naive_baseline, 2) if r.naive_baseline is not None else None,
            service=r.service,
        )
        for r in rows
    ]

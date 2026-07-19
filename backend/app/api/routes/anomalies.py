"""
Anomaly Detection route (Part 9, Tab 3).

Per spec, real-data anomaly results must NEVER imply a measured accuracy
figure - only the synthetic tier has ground truth. The response always
includes is_ground_truth_eval so the frontend can render the explicit
"unsupervised / for human review" disclaimer the spec requires whenever
the data did not come from the synthetic tier.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.db.models import Anomaly
from app.db.session import get_db

router = APIRouter(prefix="/anomalies", tags=["anomaly_detection"])


class AnomalyOut(BaseModel):
    resource_id: str
    date: str
    dimension_scores: dict
    incident_score: float
    severity: str | None
    is_ground_truth_eval: bool


@router.get("", response_model=list[AnomalyOut])
def list_anomalies(
    severity: str | None = Query(None),
    limit: int = Query(100, le=1000),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AnomalyOut]:
    query = db.query(Anomaly).filter(Anomaly.organization_id == current_user.organization_id)
    if severity:
        query = query.filter(Anomaly.severity == severity)

    rows = query.order_by(Anomaly.incident_score.desc()).limit(limit).all()
    return [
        AnomalyOut(
            resource_id=r.resource_id,
            date=r.date.isoformat(),
            dimension_scores=r.dimension_scores or {},
            incident_score=r.incident_score,
            severity=r.severity,
            is_ground_truth_eval=r.is_ground_truth_eval,
        )
        for r in rows
    ]

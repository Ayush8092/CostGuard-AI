"""
Recommendations route (Part 9, Tab 6). Serves the ranked recommendation
list (already sorted by impact_score at write time) plus the
recommendation-layer evaluation metrics (Part 4.7).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.db.models import Recommendation
from app.db.session import get_db

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


class RecommendationOut(BaseModel):
    id: str
    resource_id: str
    action: str
    estimated_savings: float
    confidence: float
    reason: str | None
    supporting_rule: str | None
    impact_tier: str | None
    impact_score: float | None
    status: str


class RecommendationLayerMetrics(BaseModel):
    total_recommendations: int
    avg_estimated_monthly_savings: float
    avg_confidence: float


@router.get("", response_model=list[RecommendationOut])
def list_recommendations(
    impact_tier: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RecommendationOut]:
    query = db.query(Recommendation).filter(Recommendation.organization_id == current_user.organization_id)
    if impact_tier:
        query = query.filter(Recommendation.impact_tier == impact_tier)
    if status_filter:
        query = query.filter(Recommendation.status == status_filter)

    rows = query.order_by(Recommendation.impact_score.desc()).all()
    return [
        RecommendationOut(
            id=r.id, resource_id=r.resource_id, action=r.action,
            estimated_savings=r.estimated_savings, confidence=r.confidence,
            reason=r.reason, supporting_rule=r.supporting_rule,
            impact_tier=r.impact_tier, impact_score=r.impact_score, status=r.status,
        )
        for r in rows
    ]


@router.get("/evaluation", response_model=RecommendationLayerMetrics)
def get_recommendation_layer_metrics(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecommendationLayerMetrics:
    org_id = current_user.organization_id
    total = db.query(func.count(Recommendation.id)).filter(Recommendation.organization_id == org_id).scalar() or 0
    avg_savings = db.query(func.coalesce(func.avg(Recommendation.estimated_savings), 0.0)).filter(
        Recommendation.organization_id == org_id
    ).scalar() or 0.0
    avg_confidence = db.query(func.coalesce(func.avg(Recommendation.confidence), 0.0)).filter(
        Recommendation.organization_id == org_id
    ).scalar() or 0.0

    return RecommendationLayerMetrics(
        total_recommendations=int(total),
        avg_estimated_monthly_savings=round(float(avg_savings), 2),
        avg_confidence=round(float(avg_confidence), 2),
    )


@router.patch("/{recommendation_id}/status")
def update_recommendation_status(
    recommendation_id: str,
    new_status: str = Query(..., pattern="^(open|accepted|dismissed)$"),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    rec = db.query(Recommendation).filter(
        Recommendation.id == recommendation_id,
        Recommendation.organization_id == current_user.organization_id,
    ).first()
    if rec is None:
        return {"updated": False, "error": "recommendation not found"}
    rec.status = new_status
    db.commit()
    return {"updated": True, "id": recommendation_id, "status": new_status}

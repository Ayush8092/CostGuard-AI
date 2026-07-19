"""
Waste Classification route (Part 9, Tab 4). Returns the latest waste
bucket per resource plus the SHAP top-contributing-features payload
computed at training time (Part 3 explainability) for the dashboard's
explanation panel.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.db.models import WasteClassification
from app.db.session import get_db

router = APIRouter(prefix="/waste", tags=["waste_classification"])


class WasteClassificationOut(BaseModel):
    resource_id: str
    date: str
    waste_score: float
    bucket: str | None
    predicted_bucket: str | None
    shap_top_features: dict | None


@router.get("", response_model=list[WasteClassificationOut])
def list_waste_classifications(
    bucket: str | None = Query(None),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[WasteClassificationOut]:
    # Latest row per resource_id (subquery on max(date)), scoped to this org.
    org_id = current_user.organization_id
    latest_dates = (
        db.query(WasteClassification.resource_id, func.max(WasteClassification.date).label("max_date"))
        .filter(WasteClassification.organization_id == org_id)
        .group_by(WasteClassification.resource_id)
        .subquery()
    )

    query = db.query(WasteClassification).join(
        latest_dates,
        (WasteClassification.resource_id == latest_dates.c.resource_id)
        & (WasteClassification.date == latest_dates.c.max_date),
    ).filter(WasteClassification.organization_id == org_id)

    if bucket:
        query = query.filter(WasteClassification.bucket == bucket)

    rows = query.all()
    return [
        WasteClassificationOut(
            resource_id=r.resource_id,
            date=r.date.isoformat(),
            waste_score=r.waste_score,
            bucket=r.bucket,
            predicted_bucket=r.predicted_bucket,
            shap_top_features=r.shap_top_features,
        )
        for r in rows
    ]

"""
Executive Insights route (Feature 3).
Stored once per dataset. Never regenerated automatically on dashboard load.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, require_role
from app.db.models import ExecutiveInsight, UploadedDataset, ProcessedTelemetry
from app.db.models import Anomaly, ForecastResult, Recommendation, WasteClassification
from app.db.session import get_db
from sqlalchemy import func

router = APIRouter(prefix="/insights", tags=["insights"])


class InsightOut(BaseModel):
    id: str
    dataset_id: str
    dataset_name: str | None
    insight_text: str
    metrics_snapshot: dict | None
    created_at: str


class GenerateRequest(BaseModel):
    dataset_id: str | None = None


def _active_dataset(db: Session, org_id: str) -> UploadedDataset | None:
    return db.query(UploadedDataset).filter(
        UploadedDataset.organization_id == org_id,
        UploadedDataset.active_flag.is_(True),
    ).first()


def _build_snapshot(db: Session, org_id: str, dataset_id: str) -> dict:
    try:
        total = db.query(func.coalesce(func.sum(ProcessedTelemetry.cost), 0.0)).filter(
            ProcessedTelemetry.organization_id == org_id,
            ProcessedTelemetry.dataset_id == dataset_id,
        ).scalar() or 0.0
        anomalies = db.query(func.count(Anomaly.id)).filter(
            Anomaly.organization_id == org_id).scalar() or 0
        savings = db.query(func.coalesce(func.sum(Recommendation.estimated_savings), 0.0)).filter(
            Recommendation.organization_id == org_id,
            Recommendation.status == "open").scalar() or 0.0
        idle = db.query(func.count(WasteClassification.id)).filter(
            WasteClassification.organization_id == org_id,
            WasteClassification.bucket.in_(["Idle", "Critical Waste"])).scalar() or 0
        fc = db.query(ForecastResult).filter(
            ForecastResult.organization_id == org_id,
            ForecastResult.level == "org_total",
        ).order_by(ForecastResult.forecast_date.desc()).first()
        return {
            "total_spend": round(float(total), 2),
            "anomaly_count": int(anomalies),
            "potential_savings": round(float(savings), 2),
            "idle_resources": int(idle),
            "forecast_next": round(float(fc.forecast), 2) if fc else None,
        }
    except Exception:
        return {}


def _generate_text(snapshot: dict, name: str) -> str:
    try:
        from app.llm.client import LlmClient, GROUNDING_SYSTEM_PROMPT
        import json
        client = LlmClient()
        prompt = (
            f"Dataset: {name}\n\nReal metrics:\n{json.dumps(snapshot, indent=2)}\n\n"
            "Write 4 concise executive insight bullets: 1) total spend, "
            "2) anomalies, 3) savings opportunity, 4) forecast. "
            "Start each with •. Use exact numbers from context only."
        )
        r = client.complete(GROUNDING_SYSTEM_PROMPT, prompt, max_tokens=300)
        if not r.is_stub:
            return r.text
    except Exception:
        pass
    lines = []
    if snapshot.get("total_spend"):
        lines.append(f"• Total cloud spend: ${snapshot['total_spend']:,.2f}")
    if snapshot.get("anomaly_count") is not None:
        lines.append(f"• Anomalies detected: {snapshot['anomaly_count']}")
    if snapshot.get("potential_savings"):
        lines.append(f"• Potential monthly savings: ${snapshot['potential_savings']:,.2f}")
    if snapshot.get("forecast_next"):
        lines.append(f"• Forecast (next period): ${snapshot['forecast_next']:,.2f}")
    if snapshot.get("idle_resources"):
        lines.append(f"• Idle/critical waste resources: {snapshot['idle_resources']}")
    return "\n".join(lines) if lines else "Upload a dataset and run the ML pipeline to generate insights."


@router.get("/active", response_model=InsightOut | None)
def get_active_insight(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InsightOut | None:
    active = _active_dataset(db, current_user.organization_id)
    if not active:
        return None
    row = db.query(ExecutiveInsight).filter(
        ExecutiveInsight.organization_id == current_user.organization_id,
        ExecutiveInsight.dataset_id == active.id,
    ).order_by(ExecutiveInsight.created_at.desc()).first()
    if not row:
        return None
    return InsightOut(
        id=str(row.id), dataset_id=str(row.dataset_id),
        dataset_name=active.dataset_name,
        insight_text=row.insight_text,
        metrics_snapshot=row.metrics_snapshot,
        created_at=row.created_at.isoformat() if row.created_at else "",
    )


@router.post("/generate", response_model=InsightOut)
def generate_insight(
    payload: GenerateRequest,
    current_user: CurrentUser = Depends(require_role("analyst")),
    db: Session = Depends(get_db),
) -> InsightOut:
    org_id = current_user.organization_id
    if payload.dataset_id:
        dataset = db.query(UploadedDataset).filter(
            UploadedDataset.id == payload.dataset_id,
            UploadedDataset.organization_id == org_id,
        ).first()
    else:
        dataset = _active_dataset(db, org_id)
    if not dataset:
        raise HTTPException(404, "No dataset found. Upload a CSV first.")

    snapshot = _build_snapshot(db, org_id, str(dataset.id))
    text = _generate_text(snapshot, dataset.dataset_name or dataset.original_filename or "")

    insight = ExecutiveInsight(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        dataset_id=str(dataset.id),
        insight_text=text,
        metrics_snapshot=snapshot,
        created_at=datetime.now(timezone.utc),
    )
    db.add(insight)
    db.commit()

    return InsightOut(
        id=str(insight.id), dataset_id=str(insight.dataset_id),
        dataset_name=dataset.dataset_name,
        insight_text=text, metrics_snapshot=snapshot,
        created_at=insight.created_at.isoformat(),
    )


@router.get("/{dataset_id}", response_model=InsightOut | None)
def get_for_dataset(
    dataset_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InsightOut | None:
    dataset = db.query(UploadedDataset).filter(
        UploadedDataset.id == dataset_id,
        UploadedDataset.organization_id == current_user.organization_id,
    ).first()
    if not dataset:
        raise HTTPException(404, "Dataset not found")
    row = db.query(ExecutiveInsight).filter(
        ExecutiveInsight.organization_id == current_user.organization_id,
        ExecutiveInsight.dataset_id == dataset_id,
    ).order_by(ExecutiveInsight.created_at.desc()).first()
    if not row:
        return None
    return InsightOut(
        id=str(row.id), dataset_id=str(row.dataset_id),
        dataset_name=dataset.dataset_name,
        insight_text=row.insight_text,
        metrics_snapshot=row.metrics_snapshot,
        created_at=row.created_at.isoformat() if row.created_at else "",
    )

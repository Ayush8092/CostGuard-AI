"""
Dataset management routes (Feature 1 + 2 + 4).

POST /datasets/upload          - upload CSV with analysis mode
GET  /datasets                 - analysis history
GET  /datasets/active          - currently active dataset
POST /datasets/{id}/activate   - switch active dataset
GET  /datasets/{id}/status     - upload progress polling
POST /datasets/reset           - safe reset with confirmation
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, require_role
from app.core.config import get_settings
from app.db.models import (
    Anomaly, ForecastResult, IncidentScore, Recommendation,
    UploadedDataset, WasteClassification, WeeklyReport, ProcessedTelemetry,
)
from app.db.session import get_db

router = APIRouter(prefix="/datasets", tags=["datasets"])


# ── Schemas ───────────────────────────────────────────────────────────────

class DatasetOut(BaseModel):
    id: str
    dataset_name: str | None
    original_filename: str
    upload_mode: str
    status: str
    progress_pct: int
    row_count: int | None
    active_flag: bool
    created_at: str
    column_mapping: dict | None


class UploadResponse(BaseModel):
    dataset_id: str
    status: str
    original_filename: str
    upload_mode: str


class UploadStatusResponse(BaseModel):
    dataset_id: str
    status: str
    progress_pct: int
    row_count: int | None
    error_message: str | None
    column_mapping: dict | None


class ResetRequest(BaseModel):
    confirmation: str


class ResetResponse(BaseModel):
    deleted_datasets: int
    deleted_forecasts: int
    deleted_anomalies: int
    deleted_waste: int
    deleted_recommendations: int
    message: str


# ── Helpers ───────────────────────────────────────────────────────────────

def _deactivate_all(db: Session, org_id: str) -> None:
    """Mark every dataset for this org as inactive."""
    db.query(UploadedDataset).filter(
        UploadedDataset.organization_id == org_id,
    ).update({"active_flag": False}, synchronize_session=False)


def _to_out(d: UploadedDataset) -> DatasetOut:
    return DatasetOut(
        id=str(d.id),
        dataset_name=d.dataset_name,
        original_filename=d.original_filename or "",
        upload_mode=d.upload_mode or "continuous",
        status=d.status or "unknown",
        progress_pct=d.progress_pct or 0,
        row_count=d.row_count,
        active_flag=bool(d.active_flag),
        created_at=d.created_at.isoformat() if d.created_at else "",
        column_mapping=d.column_mapping,
    )


# ── Routes ────────────────────────────────────────────────────────────────

@router.post("/upload", response_model=UploadResponse)
def upload_dataset(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    upload_mode: str = "continuous",
    dataset_name: str | None = None,
    current_user: CurrentUser = Depends(require_role("analyst")),
    db: Session = Depends(get_db),
) -> UploadResponse:
    if upload_mode not in ("new_analysis", "continuous"):
        raise HTTPException(400, "upload_mode must be 'new_analysis' or 'continuous'")

    settings = get_settings()
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    dataset_id = str(uuid.uuid4())
    storage_path = os.path.join(settings.UPLOAD_DIR, f"{dataset_id}_{file.filename}")
    with open(storage_path, "wb") as f:
        f.write(file.file.read())

    if upload_mode == "new_analysis":
        _deactivate_all(db, current_user.organization_id)

    dataset = UploadedDataset(
        id=dataset_id,
        organization_id=current_user.organization_id,
        uploaded_by_user_id=current_user.id,
        original_filename=file.filename,
        dataset_name=dataset_name or file.filename,
        storage_path=storage_path,
        upload_mode=upload_mode,
        status="queued",
        progress_pct=0,
        active_flag=(upload_mode == "new_analysis"),
        created_at=datetime.now(timezone.utc),
    )
    db.add(dataset)
    db.commit()

    background_tasks.add_task(
        _process_dataset,
        dataset_id,
        current_user.organization_id,
        upload_mode,
    )

    return UploadResponse(
        dataset_id=dataset_id,
        status="queued",
        original_filename=file.filename or "",
        upload_mode=upload_mode,
    )


@router.get("", response_model=list[DatasetOut])
def list_datasets(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DatasetOut]:
    rows = db.query(UploadedDataset).filter(
        UploadedDataset.organization_id == current_user.organization_id,
    ).order_by(UploadedDataset.created_at.desc()).all()
    return [_to_out(d) for d in rows]


@router.get("/active", response_model=DatasetOut | None)
def get_active(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DatasetOut | None:
    d = db.query(UploadedDataset).filter(
        UploadedDataset.organization_id == current_user.organization_id,
        UploadedDataset.active_flag.is_(True),
    ).first()
    return _to_out(d) if d else None


@router.post("/{dataset_id}/activate")
def activate_dataset(
    dataset_id: str,
    current_user: CurrentUser = Depends(require_role("analyst")),
    db: Session = Depends(get_db),
) -> dict:
    dataset = db.query(UploadedDataset).filter(
        UploadedDataset.id == dataset_id,
        UploadedDataset.organization_id == current_user.organization_id,
    ).first()
    if not dataset:
        raise HTTPException(404, "Dataset not found")
    if dataset.status != "done":
        raise HTTPException(400, f"Dataset not ready (status: {dataset.status})")

    _deactivate_all(db, current_user.organization_id)
    dataset.active_flag = True
    db.commit()

    try:
        from app.core.cache import redis_delete
        redis_delete(f"dashboard:{current_user.organization_id}")
    except Exception:
        pass

    return {"activated": True, "dataset_id": dataset_id,
            "dataset_name": dataset.dataset_name}


@router.get("/{dataset_id}/status", response_model=UploadStatusResponse)
def get_status(
    dataset_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UploadStatusResponse:
    d = db.query(UploadedDataset).filter(
        UploadedDataset.id == dataset_id,
        UploadedDataset.organization_id == current_user.organization_id,
    ).first()
    if not d:
        return UploadStatusResponse(
            dataset_id=dataset_id, status="not_found",
            progress_pct=0, row_count=None,
            error_message=None, column_mapping=None,
        )
    return UploadStatusResponse(
        dataset_id=str(d.id), status=d.status,
        progress_pct=d.progress_pct or 0, row_count=d.row_count,
        error_message=d.error_message, column_mapping=d.column_mapping,
    )


@router.post("/reset", response_model=ResetResponse)
def reset_analysis(
    payload: ResetRequest,
    current_user: CurrentUser = Depends(require_role("analyst")),
    db: Session = Depends(get_db),
) -> ResetResponse:
    if payload.confirmation != "RESET":
        raise HTTPException(400, "Confirmation must be the string 'RESET'")

    org = current_user.organization_id

    n_ds   = db.query(func.count(UploadedDataset.id)).filter(UploadedDataset.organization_id == org).scalar() or 0
    n_fc   = db.query(func.count(ForecastResult.id)).filter(ForecastResult.organization_id == org).scalar() or 0
    n_an   = db.query(func.count(Anomaly.id)).filter(Anomaly.organization_id == org).scalar() or 0
    n_wc   = db.query(func.count(WasteClassification.id)).filter(WasteClassification.organization_id == org).scalar() or 0
    n_rec  = db.query(func.count(Recommendation.id)).filter(Recommendation.organization_id == org).scalar() or 0

    db.query(Recommendation).filter(Recommendation.organization_id == org).delete(synchronize_session=False)
    db.query(WasteClassification).filter(WasteClassification.organization_id == org).delete(synchronize_session=False)
    db.query(Anomaly).filter(Anomaly.organization_id == org).delete(synchronize_session=False)
    db.query(IncidentScore).filter(IncidentScore.organization_id == org).delete(synchronize_session=False)
    db.query(ForecastResult).filter(ForecastResult.organization_id == org).delete(synchronize_session=False)
    db.query(WeeklyReport).filter(WeeklyReport.organization_id == org).delete(synchronize_session=False)
    db.query(ProcessedTelemetry).filter(ProcessedTelemetry.organization_id == org).delete(synchronize_session=False)
    db.query(UploadedDataset).filter(UploadedDataset.organization_id == org).delete(synchronize_session=False)
    db.commit()

    try:
        from app.core.cache import redis_delete
        redis_delete(f"dashboard:{org}")
    except Exception:
        pass

    return ResetResponse(
        deleted_datasets=int(n_ds),
        deleted_forecasts=int(n_fc),
        deleted_anomalies=int(n_an),
        deleted_waste=int(n_wc),
        deleted_recommendations=int(n_rec),
        message="Reset complete. Previously downloaded reports are unaffected.",
    )


# ── Background processing ─────────────────────────────────────────────────

def _process_dataset(dataset_id: str, organization_id: str, upload_mode: str) -> None:
    from app.db.session import SessionLocal
    from app.data.csv_upload import ingest_csv
    import uuid as _uuid

    db = SessionLocal()
    try:
        dataset = db.query(UploadedDataset).filter(UploadedDataset.id == dataset_id).first()
        if not dataset:
            return

        dataset.status = "processing"
        dataset.progress_pct = 10
        db.commit()

        try:
            result = ingest_csv(dataset.storage_path, organization_id=organization_id)
        except Exception as e:
            dataset.status = "failed"
            dataset.error_message = str(e)
            db.commit()
            return

        dataset.progress_pct = 40
        dataset.column_mapping = result.column_mapping
        db.commit()

        # new_analysis: clear previous telemetry so datasets never mix
        if upload_mode == "new_analysis":
            db.query(ProcessedTelemetry).filter(
                ProcessedTelemetry.organization_id == organization_id,
            ).delete(synchronize_session=False)
            db.commit()

        dataset.progress_pct = 60
        db.commit()

        # Load rows — tag each with dataset_id (UUID FK) not dataset_version
        for row in result.df.itertuples(index=False):
            d = row._asdict()
            db.add(ProcessedTelemetry(
                id=str(_uuid.uuid4()),
                organization_id=organization_id,
                dataset_id=dataset_id,          # UUID FK — links to UploadedDataset
                dataset_version=dataset_id,     # kept for backward compat
                source_tier="csv_upload",
                date=d.get("date"),
                service=d.get("service", "unknown"),
                resource_id=d.get("resource_id", "unknown"),
                cost=d.get("cost", 0.0),
                cpu_avg_pct=d.get("cpu_avg_pct"),
                memory_avg_pct=d.get("memory_avg_pct"),
                region=d.get("region"),
                instance_type=d.get("instance_type"),
                runtime_days=d.get("runtime_days"),
                cost_growth_rate=d.get("cost_growth_rate"),
                anomaly_history_count=d.get("anomaly_history_count", 0),
            ))

        dataset.status = "done"
        dataset.progress_pct = 100
        dataset.row_count = len(result.df)
        dataset.processed_at = datetime.now(timezone.utc)
        db.commit()

        # Trigger ML pipeline
        try:
            from app.workers.scheduler import trigger_post_upload
            trigger_post_upload(organization_id)
        except Exception:
            pass

    except Exception as e:
        db.rollback()
        ds = db.query(UploadedDataset).filter(UploadedDataset.id == dataset_id).first()
        if ds:
            ds.status = "failed"
            ds.error_message = f"Processing error: {e}"
            db.commit()
    finally:
        db.close()

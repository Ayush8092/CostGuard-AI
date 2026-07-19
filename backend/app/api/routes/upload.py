"""
CSV Upload route (Part 9, Tab 10 - Settings / Part 1 Tier 3).

Per Part 8: "Background workers for heavy tasks (CSV processing) via a
queue... with a status endpoint (queued -> processing 45% -> done)
instead of blocking the request." The upload endpoint writes the file
to disk, creates an UploadedDataset row with status=queued, and returns
immediately; actual processing happens in a background task (see
app/workers/csv_processor.py) which updates progress_pct as it runs.
"""
from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, require_role
from app.core.config import get_settings
from app.db.models import UploadedDataset
from app.db.session import get_db
from app.workers.csv_processor import process_uploaded_csv

router = APIRouter(prefix="/upload-csv", tags=["csv_upload"])


class UploadResponse(BaseModel):
    dataset_id: str
    status: str
    original_filename: str


class UploadStatusResponse(BaseModel):
    dataset_id: str
    status: str
    progress_pct: int
    row_count: int | None
    error_message: str | None


@router.post("", response_model=UploadResponse)
def upload_csv(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(require_role("analyst")),
    db: Session = Depends(get_db),
) -> UploadResponse:
    settings = get_settings()
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    dataset_id = str(uuid.uuid4())
    storage_path = os.path.join(settings.UPLOAD_DIR, f"{dataset_id}_{file.filename}")
    with open(storage_path, "wb") as f:
        f.write(file.file.read())

    dataset = UploadedDataset(
        id=dataset_id,
        organization_id=current_user.organization_id,
        uploaded_by_user_id=current_user.id,
        original_filename=file.filename,
        storage_path=storage_path,
        status="queued",
        progress_pct=0,
    )
    db.add(dataset)
    db.commit()

    background_tasks.add_task(process_uploaded_csv, dataset_id, current_user.organization_id)

    return UploadResponse(dataset_id=dataset_id, status="queued", original_filename=file.filename)


@router.get("/{dataset_id}/status", response_model=UploadStatusResponse)
def get_upload_status(
    dataset_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UploadStatusResponse:
    dataset = db.query(UploadedDataset).filter(
        UploadedDataset.id == dataset_id,
        UploadedDataset.organization_id == current_user.organization_id,
    ).first()
    if dataset is None:
        return UploadStatusResponse(dataset_id=dataset_id, status="not_found", progress_pct=0, row_count=None, error_message=None)

    return UploadStatusResponse(
        dataset_id=dataset.id, status=dataset.status, progress_pct=dataset.progress_pct,
        row_count=dataset.row_count, error_message=dataset.error_message,
    )

"""
Background CSV processing worker (Part 8). Runs as a FastAPI
BackgroundTask for v1 (simple, zero extra infra). The same function
signature can be wrapped by RQ/Celery later without changing the
ingestion logic itself - the task-queue mechanism is decoupled from
what the task actually does.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.data.csv_upload import ingest_csv
from app.data.validation import validate_dataframe
from app.db.models import AuditLog, ProcessedTelemetry, UploadedDataset
from app.db.session import SessionLocal


def process_uploaded_csv(dataset_id: str, organization_id: str) -> None:
    db = SessionLocal()
    try:
        dataset = db.query(UploadedDataset).filter(UploadedDataset.id == dataset_id).first()
        if dataset is None:
            return

        dataset.status = "processing"
        dataset.progress_pct = 10
        db.commit()

        try:
            result = ingest_csv(dataset.storage_path, organization_id=organization_id)
        except ValueError as e:
            dataset.status = "failed"
            dataset.error_message = str(e)
            db.commit()
            return

        dataset.progress_pct = 50
        dataset.column_mapping = result.column_mapping
        db.commit()

        # Persist validation failures to the audit log, never silently drop rows (Part 1).
        for record in result.validation_report.to_audit_records(organization_id, source_tier="csv_upload"):
            db.add(AuditLog(
                organization_id=record["organization_id"],
                event_type=record["event_type"],
                severity=record["severity"],
                details=record["details"],
            ))

        dataset.progress_pct = 70
        db.commit()

        import uuid
        for row in result.df.itertuples(index=False):
            row_dict = row._asdict()
            db.add(ProcessedTelemetry(
                id=str(uuid.uuid4()),
                organization_id=organization_id,
                source_tier="csv_upload",
                dataset_version=dataset_id,
                date=row_dict["date"],
                service=row_dict.get("service", "unknown"),
                resource_id=row_dict.get("resource_id", "unknown"),
                cost=row_dict.get("cost", 0.0),
                cpu_avg_pct=row_dict.get("cpu_avg_pct"),
                memory_avg_pct=row_dict.get("memory_avg_pct"),
                region=row_dict.get("region"),
                instance_type=row_dict.get("instance_type"),
                runtime_days=row_dict.get("runtime_days"),
                cost_growth_rate=row_dict.get("cost_growth_rate"),
                anomaly_history_count=row_dict.get("anomaly_history_count", 0),
            ))

        dataset.progress_pct = 100
        dataset.status = "done"
        dataset.row_count = len(result.df)
        dataset.processed_at = datetime.now(timezone.utc)
        db.commit()

        from app.workers.scheduler import trigger_post_upload
        trigger_post_upload(organization_id)

    except Exception as e:  # noqa: BLE001 - background task boundary; must not crash silently
        db.rollback()
        dataset = db.query(UploadedDataset).filter(UploadedDataset.id == dataset_id).first()
        if dataset:
            dataset.status = "failed"
            dataset.error_message = f"Unexpected error during processing: {e}"
            db.commit()
    finally:
        db.close()

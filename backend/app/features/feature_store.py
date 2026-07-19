"""
Lightweight Feature Store (Part 2).

A versioned feature table in PostgreSQL that decouples feature
computation from training/serving: features are computed once here,
written to the feature_store table, and read by all downstream models
(forecasting, anomaly detection, waste classification).

This is a legitimate feature store BY FUNCTION - it is a custom,
self-built implementation. It does not use and does not claim to use
a tool like Feast.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.models import FeatureStore

FEATURE_VERSION = "v1"

# Columns from the engineered dataframe that get persisted as the feature
# vector (everything except identifying columns, which become their own
# FeatureStore fields rather than living inside the JSON blob).
IDENTIFYING_COLS = {"date", "resource_id", "organization_id"}


def write_features_to_store(
    db: Session,
    organization_id: str,
    featured_df: pd.DataFrame,
    feature_version: str = FEATURE_VERSION,
    batch_size: int = 1000,
) -> int:
    """
    Upserts one feature_store row per (organization_id, resource_id, date).
    Returns the number of rows written. Uses Postgres ON CONFLICT so
    re-running feature computation for the same day is idempotent.
    """
    records = []
    for row in featured_df.itertuples(index=False):
        row_dict = row._asdict()
        date_val = row_dict.get("date")
        resource_id = row_dict.get("resource_id")
        if date_val is None or resource_id is None:
            continue

        feature_payload = {k: _json_safe(v) for k, v in row_dict.items() if k not in IDENTIFYING_COLS}

        records.append({
            "id": str(uuid.uuid4()),
            "organization_id": organization_id,
            "resource_id": str(resource_id),
            "date": pd.Timestamp(date_val).to_pydatetime(),
            "feature_version": feature_version,
            "features": feature_payload,
            "created_at": datetime.now(timezone.utc),
        })

    written = 0
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        stmt = pg_insert(FeatureStore).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=["organization_id", "resource_id", "date", "feature_version"],
            set_={"features": stmt.excluded.features, "created_at": stmt.excluded.created_at},
        )
        db.execute(stmt)
        written += len(batch)
    db.commit()
    return written


def read_features_from_store(
    db: Session,
    organization_id: str,
    resource_ids: list[str] | None = None,
    feature_version: str = FEATURE_VERSION,
) -> pd.DataFrame:
    """Reads back the feature store into a flat dataframe for model training/serving."""
    query = db.query(FeatureStore).filter(
        FeatureStore.organization_id == organization_id,
        FeatureStore.feature_version == feature_version,
    )
    if resource_ids:
        query = query.filter(FeatureStore.resource_id.in_(resource_ids))

    rows = query.all()
    flat_records = []
    for r in rows:
        rec = {"resource_id": r.resource_id, "date": r.date}
        rec.update(r.features or {})
        flat_records.append(rec)
    return pd.DataFrame(flat_records)


def _json_safe(value):
    """Coerces pandas/numpy scalar types into plain JSON-serializable Python types."""
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):  # numpy scalar
        return value.item()
    return value

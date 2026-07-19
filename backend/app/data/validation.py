"""
Data Quality Validation (Part 1) - applied to every tier before features
are computed.

Validates and flags/rejects:
  - missing timestamps
  - duplicated VM/resource IDs (for a given date)
  - impossible CPU values (>100%)
  - negative memory
  - negative prices
  - missing regions
  - inconsistent/unmappable instance types

Validation failures are returned as structured records meant to be
written to the audit_logs table (Part 7) - never silently dropped.
Callers decide whether to drop, null-out, or keep-with-flag a failing
row; this module only detects and reports.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd

from app.data.instance_specs import INSTANCE_SPEC_BY_TYPE

VALID_INSTANCE_TYPES = set(INSTANCE_SPEC_BY_TYPE.keys())


@dataclass
class ValidationFailure:
    row_index: int
    resource_id: str | None
    rule: str
    detail: str
    severity: str = "warning"  # warning | error


@dataclass
class ValidationReport:
    total_rows: int
    failures: list[ValidationFailure] = field(default_factory=list)

    def to_audit_records(self, organization_id: str | None, source_tier: str) -> list[dict]:
        ts = datetime.now(timezone.utc).isoformat()
        return [
            {
                "organization_id": organization_id,
                "event_type": "validation_failure",
                "severity": f.severity,
                "details": {
                    "source_tier": source_tier,
                    "row_index": f.row_index,
                    "resource_id": f.resource_id,
                    "rule": f.rule,
                    "detail": f.detail,
                },
                "created_at": ts,
            }
            for f in self.failures
        ]

    def summary(self) -> dict:
        by_rule: dict[str, int] = {}
        for f in self.failures:
            by_rule[f.rule] = by_rule.get(f.rule, 0) + 1
        return {
            "total_rows": self.total_rows,
            "total_failures": len(self.failures),
            "failures_by_rule": by_rule,
        }


def validate_dataframe(
    df: pd.DataFrame,
    require_region: bool = False,
    require_instance_type_known: bool = False,
) -> ValidationReport:
    """
    Runs all validation rules against a dataframe already shaped like the
    internal schema (date, resource_id, cost, cpu_avg_pct, memory_avg_pct,
    region, instance_type, ...). Columns that don't exist in a given tier
    are simply skipped for the rules that need them.
    """
    failures: list[ValidationFailure] = []
    cols = set(df.columns)

    # missing timestamps
    if "date" in cols:
        missing_dates = df[df["date"].isna()]
        for idx in missing_dates.index:
            failures.append(ValidationFailure(
                row_index=int(idx), resource_id=_safe_get(df, idx, "resource_id"),
                rule="missing_timestamp", detail="date is null", severity="error",
            ))

    # duplicated resource_id for the same date
    if {"date", "resource_id"}.issubset(cols):
        dupe_mask = df.duplicated(subset=["date", "resource_id"], keep=False)
        for idx in df[dupe_mask].index:
            failures.append(ValidationFailure(
                row_index=int(idx), resource_id=_safe_get(df, idx, "resource_id"),
                rule="duplicated_resource_id", detail="duplicate (date, resource_id) pair", severity="warning",
            ))

    # impossible CPU values (>100% or <0%)
    if "cpu_avg_pct" in cols:
        bad_cpu = df[(df["cpu_avg_pct"] > 100) | (df["cpu_avg_pct"] < 0)]
        for idx, row in bad_cpu.iterrows():
            failures.append(ValidationFailure(
                row_index=int(idx), resource_id=_safe_get(df, idx, "resource_id"),
                rule="impossible_cpu_value", detail=f"cpu_avg_pct={row['cpu_avg_pct']}", severity="error",
            ))

    # negative memory
    if "memory_avg_pct" in cols:
        bad_mem = df[df["memory_avg_pct"] < 0]
        for idx, row in bad_mem.iterrows():
            failures.append(ValidationFailure(
                row_index=int(idx), resource_id=_safe_get(df, idx, "resource_id"),
                rule="negative_memory", detail=f"memory_avg_pct={row['memory_avg_pct']}", severity="error",
            ))

    # negative prices
    if "cost" in cols:
        bad_cost = df[df["cost"] < 0]
        for idx, row in bad_cost.iterrows():
            failures.append(ValidationFailure(
                row_index=int(idx), resource_id=_safe_get(df, idx, "resource_id"),
                rule="negative_price", detail=f"cost={row['cost']}", severity="error",
            ))

    # missing regions
    if require_region and "region" in cols:
        missing_region = df[df["region"].isna() | (df["region"].astype(str).str.strip() == "")]
        for idx in missing_region.index:
            failures.append(ValidationFailure(
                row_index=int(idx), resource_id=_safe_get(df, idx, "resource_id"),
                rule="missing_region", detail="region is null or empty", severity="warning",
            ))

    # inconsistent/unmappable instance types
    if require_instance_type_known and "instance_type" in cols:
        known_mask = df["instance_type"].isna() | df["instance_type"].isin(VALID_INSTANCE_TYPES)
        for idx in df[~known_mask].index:
            failures.append(ValidationFailure(
                row_index=int(idx), resource_id=_safe_get(df, idx, "resource_id"),
                rule="unmappable_instance_type",
                detail=f"instance_type={df.loc[idx, 'instance_type']!r} not in reference table",
                severity="warning",
            ))

    return ValidationReport(total_rows=len(df), failures=failures)


def _safe_get(df: pd.DataFrame, idx, col: str):
    if col in df.columns:
        try:
            return str(df.loc[idx, col])
        except Exception:
            return None
    return None


if __name__ == "__main__":
    import pandas as pd

    sample = pd.DataFrame({
        "date": ["2024-01-01", None, "2024-01-02"],
        "resource_id": ["r1", "r2", "r1"],
        "cost": [10.0, -5.0, 20.0],
        "cpu_avg_pct": [150.0, 50.0, 30.0],
        "memory_avg_pct": [40.0, -10.0, 20.0],
        "region": ["us-east-1", None, "us-east-1"],
    })
    report = validate_dataframe(sample, require_region=True)
    print(report.summary())
    for f in report.failures:
        print(f)

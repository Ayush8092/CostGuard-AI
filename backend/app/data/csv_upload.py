"""
Tier 3 - CSV Upload (bring-your-own data), Part 1.

Pipeline: Upload -> Schema Validation -> Column Mapping -> Feature
Engineering -> ML Pipeline.

Required columns: date, service, resource_id, cost.
Optional: cpu_avg_pct, memory_avg_pct, instance_type, region.

Graceful degradation: raw AWS Cost and Usage Report (CUR) exports
commonly have NO utilization columns, because utilization comes from
CloudWatch, not billing data. When cpu_avg_pct / memory_avg_pct are
missing, we automatically drop those terms from the waste-score formula
(Part 3) and re-normalize the remaining weights rather than fail or
silently impute fake values.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

from app.data.validation import ValidationReport, validate_dataframe

REQUIRED_COLUMNS = ["date", "service", "resource_id", "cost"]
OPTIONAL_COLUMNS = ["cpu_avg_pct", "memory_avg_pct", "instance_type", "region", "account_id", "usage_hours"]

# Common header aliases seen in real-world exports (AWS CUR, generic billing exports, etc.)
HEADER_ALIASES: dict[str, list[str]] = {
    "date": ["date", "usagedate", "billingdate", "usagestartdate", "day"],
    "service": ["service", "productname", "servicename", "product"],
    "resource_id": ["resourceid", "resource", "instanceid", "lineitemresourceid"],
    "cost": ["cost", "amount", "unblendedcost", "totalcost", "charge"],
    "cpu_avg_pct": ["cpuavgpct", "cpuutilization", "cpupercent", "avgcpu"],
    "memory_avg_pct": ["memoryavgpct", "memoryutilization", "memorypercent", "avgmemory"],
    "instance_type": ["instancetype", "instance", "type"],
    "region": ["region", "awsregion", "location"],
    "account_id": ["accountid", "account", "lineitemusageaccountid"],
    "usage_hours": ["usagehours", "hours", "usageamount"],
}


def _norm(s: str) -> str:
    return re.sub(r"[\s_\-]+", "", s.strip().lower())


@dataclass
class ColumnMappingResult:
    mapping: dict[str, str]  # internal_name -> original_column_name
    unmapped_required: list[str] = field(default_factory=list)
    missing_optional: list[str] = field(default_factory=list)


def map_columns(columns: list[str]) -> ColumnMappingResult:
    norm_lookup = {_norm(c): c for c in columns}
    mapping: dict[str, str] = {}

    for internal_name, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            if alias in norm_lookup:
                mapping[internal_name] = norm_lookup[alias]
                break

    unmapped_required = [c for c in REQUIRED_COLUMNS if c not in mapping]
    missing_optional = [c for c in OPTIONAL_COLUMNS if c not in mapping]

    return ColumnMappingResult(mapping=mapping, unmapped_required=unmapped_required, missing_optional=missing_optional)


@dataclass
class CsvIngestResult:
    df: pd.DataFrame
    column_mapping: dict[str, str]
    missing_optional: list[str]
    waste_score_weights_used: dict[str, float]
    validation_report: ValidationReport


def get_waste_score_weights(available_columns: set[str]) -> dict[str, float]:
    """
    Part 3 waste_score formula default weights, re-normalized if a signal
    is unavailable (graceful degradation for CUR-style exports with no
    utilization data).
    """
    base_weights = {
        "cpu_term": 0.30,
        "memory_term": 0.20,
        "cost_growth_term": 0.20,
        "idle_days_term": 0.20,
        "anomaly_history_term": 0.10,
    }
    signal_requirements = {
        "cpu_term": "cpu_avg_pct",
        "memory_term": "memory_avg_pct",
        "cost_growth_term": "cost_growth_rate",
        "idle_days_term": "cpu_avg_pct",  # idle days derived from cpu history
        "anomaly_history_term": "anomaly_history_count",
    }
    usable = {k: w for k, w in base_weights.items() if signal_requirements[k] in available_columns}
    if not usable:
        return {}
    total = sum(usable.values())
    return {k: round(w / total, 4) for k, w in usable.items()}


def ingest_csv(file_path: str, organization_id: str | None = None) -> CsvIngestResult:
    df = pd.read_csv(file_path)
    mapping_result = map_columns(list(df.columns))

    if mapping_result.unmapped_required:
        raise ValueError(
            f"Uploaded CSV is missing required columns (or unrecognized headers): "
            f"{mapping_result.unmapped_required}. Found columns: {list(df.columns)}"
        )

    # Build a dataframe in the internal schema shape using only columns we could map
    internal_df = pd.DataFrame()
    for internal_name, original_col in mapping_result.mapping.items():
        internal_df[internal_name] = df[original_col]

    internal_df["date"] = pd.to_datetime(internal_df["date"], errors="coerce")
    internal_df["cost"] = pd.to_numeric(internal_df["cost"], errors="coerce")
    if "cpu_avg_pct" in internal_df.columns:
        internal_df["cpu_avg_pct"] = pd.to_numeric(internal_df["cpu_avg_pct"], errors="coerce")
    if "memory_avg_pct" in internal_df.columns:
        internal_df["memory_avg_pct"] = pd.to_numeric(internal_df["memory_avg_pct"], errors="coerce")

    internal_df = internal_df.sort_values(["resource_id", "date"]).reset_index(drop=True)
    internal_df["runtime_days"] = internal_df.groupby("resource_id").cumcount() + 1
    growth = internal_df.groupby("resource_id")["cost"].pct_change(fill_method=None)
    internal_df["cost_growth_rate"] = growth.fillna(0.0).astype(float)
    internal_df["anomaly_history_count"] = 0  # populated later by the anomaly model, not at ingest time

    available_cols = set(internal_df.columns)
    weights = get_waste_score_weights(available_cols)

    validation_report = validate_dataframe(
        internal_df,
        require_region="region" in available_cols,
        require_instance_type_known="instance_type" in available_cols,
    )

    return CsvIngestResult(
        df=internal_df,
        column_mapping=mapping_result.mapping,
        missing_optional=mapping_result.missing_optional,
        waste_score_weights_used=weights,
        validation_report=validation_report,
    )


if __name__ == "__main__":
    import os
    import tempfile

    # Simulate a raw AWS CUR-style export with NO utilization columns at all,
    # to prove the graceful-degradation path actually works end to end.
    csv_text = """UsageStartDate,ProductName,LineItemResourceId,UnblendedCost
2024-01-01,Amazon EC2,i-0abc123,4.50
2024-01-02,Amazon EC2,i-0abc123,4.75
2024-01-01,Amazon S3,bucket-xyz,0.80
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write(csv_text)
        tmp_path = f.name

    result = ingest_csv(tmp_path)
    print("Column mapping:", result.column_mapping)
    print("Missing optional columns:", result.missing_optional)
    print("Waste score weights (re-normalized):", result.waste_score_weights_used)
    print("Validation summary:", result.validation_report.summary())
    print(result.df)
    os.unlink(tmp_path)

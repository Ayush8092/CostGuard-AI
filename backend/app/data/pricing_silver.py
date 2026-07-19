"""
Tier 2 - Pricing Bronze -> Silver (Part 1).

Takes the schema-detected pricing files (from pricing_classifier.py) and
converts each into a standardized shape:
    instance_type, region, os, pricing_type, hourly_rate, effective_date, source_file

Standardization steps per the spec:
  - detect schema (done upstream by pricing_classifier)
  - rename columns to the canonical names
  - convert to hourly rate (on-demand/spot prices in these datasets are
    already $/hour; prediction datasets carry a predicted $/hour figure -
    both pass through unchanged, but the conversion step is explicit and
    documented here so a future vendor file billed per-minute or per-day
    has a clear place to convert)
  - standardize region/OS naming (lowercase, strip whitespace, collapse
    AWS AZ suffixes like "us-east-1b" down to region "us-east-1" where
    only an AZ is given)
  - remove duplicates
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone

import pandas as pd

from app.data.pricing_classifier import classify_pricing_directory


def _strip_az_suffix(region_or_az: str) -> str:
    """'us-east-1b' -> 'us-east-1'; 'ap-southeast-2c' -> 'ap-southeast-2'. Leaves bare regions untouched."""
    if not isinstance(region_or_az, str):
        return region_or_az
    return re.sub(r"([a-z]+-[a-z]+-\d+)[a-z]$", r"\1", region_or_az.strip())


def _standardize_os(os_value: str) -> str:
    if not isinstance(os_value, str):
        return "unknown"
    v = os_value.lower()
    if "red hat" in v or "rhel" in v:
        return "rhel"
    if "suse" in v:
        return "suse"
    if "windows" in v:
        return "windows"
    if "linux" in v or "unix" in v:
        return "linux"
    return v.strip()


def build_pricing_silver(bronze_dir: str, silver_dir: str, manifest_path: str | None = None) -> pd.DataFrame:
    os.makedirs(silver_dir, exist_ok=True)
    manifest: dict = {"stage": "pricing_silver", "created_at": datetime.now(timezone.utc).isoformat(), "files": []}

    classifications = classify_pricing_directory(bronze_dir)
    standardized_rows = []

    for result in classifications:
        file_entry = {
            "file": result.file_path,
            "classified_as": result.classified_as,
            "needs_manual_mapping": result.needs_manual_mapping,
        }
        if result.needs_manual_mapping:
            manifest["files"].append({**file_entry, "rows_extracted": 0, "note": "flagged for manual column mapping"})
            continue

        # Re-read the actual sheet data (classification only inspected columns)
        if result.file_path.lower().endswith(".csv"):
            df = pd.read_csv(result.file_path)
        else:
            df = pd.read_excel(result.file_path, sheet_name=result.sheet_name)
        df.columns = [c.strip() for c in df.columns]  # strip whitespace from headers like ' InstanceType'

        m = {k: v.strip() if isinstance(v, str) else v for k, v in result.matched_columns.items()}

        out = pd.DataFrame()
        out["instance_type"] = df[m["instance_type"]].astype(str).str.strip() if m.get("instance_type") else None
        out["region_raw"] = df[m["region"]].astype(str).str.strip() if m.get("region") else None
        out["region"] = out["region_raw"].apply(_strip_az_suffix)
        out["os"] = df[m["os"]].apply(_standardize_os) if m.get("os") else "unknown"
        out["hourly_rate"] = pd.to_numeric(df[m["price"]], errors="coerce")
        out["effective_date"] = pd.to_datetime(df[m["date"]], errors="coerce") if m.get("date") else pd.NaT
        out["pricing_type"] = result.classified_as
        out["source_file"] = os.path.basename(result.file_path)

        before = len(out)
        out = out.dropna(subset=["hourly_rate", "instance_type"])
        out = out[out["hourly_rate"] > 0]  # negative/zero prices are invalid, caught by validation too
        # Dedupe on the RAW region/AZ, not the stripped rollup region - two AZs in the
        # same region (e.g. ap-southeast-2a vs ap-southeast-2b) are distinct price points
        # and must not collide after region normalization.
        out = out.drop_duplicates(subset=["instance_type", "region_raw", "os", "pricing_type", "effective_date", "hourly_rate"])
        dropped = before - len(out)

        standardized_rows.append(out)
        file_entry["rows_extracted"] = len(out)
        file_entry["rows_dropped_invalid_or_dupe"] = dropped
        manifest["files"].append(file_entry)

    combined = pd.concat(standardized_rows, ignore_index=True) if standardized_rows else pd.DataFrame()
    out_path = os.path.join(silver_dir, "pricing_silver.csv")
    combined.to_csv(out_path, index=False)

    if manifest_path:
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

    return combined


if __name__ == "__main__":
    result = build_pricing_silver(
        bronze_dir="app/data/bronze/pricing_v1",
        silver_dir="app/data/silver/pricing_cleaned_v2",
        manifest_path="app/data/silver/pricing_cleaned_v2/manifest.json",
    )
    print(result)
    print("\nPricing types:", result["pricing_type"].value_counts().to_dict())

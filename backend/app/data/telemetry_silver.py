"""
Tier 2 - Bronze -> Silver cleaning for Bitbrains VM telemetry (Part 1).

Raw Bitbrains data arrives at ~5-minute granularity. This module:
  1. Removes duplicate (VM_ID, Datetime) rows
  2. Fixes/parses datetime
  3. Converts KB units to consistent units (KB -> MB for memory, kept as
     KBps for disk/network since that's already a rate)
  4. Handles missing values (forward-fill within a VM, then drop any
     still-missing critical fields)
  5. Sorts timestamps
  6. Resamples 5-minute data to daily granularity:
       - mean for CPU/memory utilization
       - sum for disk/network I/O (these are throughput rates; summing
         the resampled rate approximates total daily I/O volume in the
         absence of per-interval byte counts)

Output is written to the silver layer with a manifest documenting row
counts at each stage, for the reproducibility requirement in Part 1.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd


REQUIRED_COLUMNS = [
    "VM_ID", "Datetime", "CPU_Cores", "CPU_Capacity_MHz", "CPU_Usage_MHz",
    "CPU_Usage_Percent", "Memory_Provisioned_KB", "Memory_Usage_KB",
    "Disk_Read_KBps", "Disk_Write_KBps", "Network_Received_KBps", "Network_Transmitted_KBps",
]


def load_bronze_telemetry(directory: str) -> pd.DataFrame:
    """Loads and concatenates all raw Bitbrains files in a bronze directory, untouched."""
    frames = []
    for fname in sorted(os.listdir(directory)):
        if fname.lower().endswith((".xlsx", ".xls", ".csv")):
            path = os.path.join(directory, fname)
            df = pd.read_csv(path) if fname.lower().endswith(".csv") else pd.read_excel(path)
            df["_source_file"] = fname
            frames.append(df)
    if not frames:
        raise FileNotFoundError(f"No telemetry files found in {directory}")
    return pd.concat(frames, ignore_index=True)


def clean_telemetry_to_silver(
    bronze_dir: str,
    silver_dir: str,
    manifest_path: str | None = None,
) -> pd.DataFrame:
    os.makedirs(silver_dir, exist_ok=True)
    manifest: dict = {"stage": "silver", "created_at": datetime.now(timezone.utc).isoformat(), "steps": []}

    raw = load_bronze_telemetry(bronze_dir)
    manifest["steps"].append({"step": "load_bronze", "row_count": len(raw)})

    missing_cols = [c for c in REQUIRED_COLUMNS if c not in raw.columns]
    if missing_cols:
        raise ValueError(f"Bitbrains source is missing required columns: {missing_cols}")

    df = raw.copy()

    # 1. Datetime parsing - coerce errors to NaT so we can drop/flag them rather than crash
    df["Datetime"] = pd.to_datetime(df["Datetime"], errors="coerce")
    bad_dates = df["Datetime"].isna().sum()
    df = df.dropna(subset=["Datetime"])
    manifest["steps"].append({"step": "parse_datetime", "dropped_bad_dates": int(bad_dates), "row_count": len(df)})

    # 2. Remove duplicate (VM_ID, Datetime) rows
    before = len(df)
    df = df.drop_duplicates(subset=["VM_ID", "Datetime"], keep="first")
    manifest["steps"].append({"step": "drop_duplicates", "dropped": before - len(df), "row_count": len(df)})

    # 3. Sort by VM then timestamp
    df = df.sort_values(["VM_ID", "Datetime"]).reset_index(drop=True)

    # 4. Handle missing numeric values: forward-fill within each VM's own timeline,
    #    then drop rows still missing a critical field after fill
    numeric_cols = [
        "CPU_Cores", "CPU_Capacity_MHz", "CPU_Usage_MHz", "CPU_Usage_Percent",
        "Memory_Provisioned_KB", "Memory_Usage_KB", "Disk_Read_KBps", "Disk_Write_KBps",
        "Network_Received_KBps", "Network_Transmitted_KBps",
    ]
    before_na = df[numeric_cols].isna().sum().to_dict()
    df[numeric_cols] = df.groupby("VM_ID")[numeric_cols].transform(lambda s: s.ffill().bfill())
    before_drop = len(df)
    df = df.dropna(subset=["CPU_Usage_Percent", "Memory_Usage_KB"])
    manifest["steps"].append({
        "step": "handle_missing_values",
        "nulls_before_fill": {k: int(v) for k, v in before_na.items() if v > 0},
        "dropped_unfillable": before_drop - len(df),
        "row_count": len(df),
    })

    # 5. Unit normalization: KB -> MB for memory (more readable), keep *Bps as rates
    df["Memory_Provisioned_MB"] = df["Memory_Provisioned_KB"] / 1024.0
    df["Memory_Usage_MB"] = df["Memory_Usage_KB"] / 1024.0
    df["Memory_Utilization_Ratio"] = (df["Memory_Usage_KB"] / df["Memory_Provisioned_KB"]).clip(0, 1)
    df["CPU_Utilization_Ratio"] = (df["CPU_Usage_MHz"] / df["CPU_Capacity_MHz"]).clip(0, 1)

    # 6. Resample 5-minute data to daily granularity per VM
    df = df.set_index("Datetime")
    daily_frames = []
    for vm_id, grp in df.groupby("VM_ID"):
        daily = grp.resample("D").agg({
            "CPU_Cores": "first",
            "CPU_Capacity_MHz": "mean",
            "CPU_Usage_MHz": "mean",
            "CPU_Usage_Percent": "mean",
            "Memory_Provisioned_KB": "mean",
            "Memory_Usage_KB": "mean",
            "Memory_Provisioned_MB": "mean",
            "Memory_Usage_MB": "mean",
            "Memory_Utilization_Ratio": "mean",
            "CPU_Utilization_Ratio": "mean",
            "Disk_Read_KBps": "sum",
            "Disk_Write_KBps": "sum",
            "Network_Received_KBps": "sum",
            "Network_Transmitted_KBps": "sum",
        })
        daily["VM_ID"] = vm_id
        daily_frames.append(daily)

    daily_df = pd.concat(daily_frames).dropna(how="all", subset=["CPU_Usage_Percent"]).reset_index()
    daily_df = daily_df.rename(columns={"Datetime": "date"})
    manifest["steps"].append({"step": "resample_daily", "row_count": len(daily_df)})

    out_path = os.path.join(silver_dir, "bitbrains_daily_silver.csv")
    daily_df.to_csv(out_path, index=False)

    if manifest_path:
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

    return daily_df


if __name__ == "__main__":
    result = clean_telemetry_to_silver(
        bronze_dir="app/data/bronze/bitbrains_v1",
        silver_dir="app/data/silver/bitbrains_cleaned_v2",
        manifest_path="app/data/silver/bitbrains_cleaned_v2/manifest.json",
    )
    print(result)
    print("\nColumns:", list(result.columns))

"""
Telemetry Cost Estimation Engine (Part 1, Tier 2).

This is NOT just a "pricing engine" - it matches raw VM telemetry to a
standard instance type, estimates billing, computes runtime cost,
aggregates costs, and prepares ML targets. The full deterministic
process, as specified:

  1. Normalize CPU cores against standard instance-family vCPU counts.
  2. Normalize provisioned memory against standard instance-family RAM sizes.
  3. Filter candidate instance families within a reasonable size range.
  4. Compute a weighted distance score across normalized CPU + memory dimensions.
  5. Select the minimum-distance match.
  6. Record a numeric confidence score for the match.
  7. If confidence is below threshold, flag the VM for manual review
     rather than silently assigning a low-confidence match.
  8. Compute cost: daily_cost = usage_hours x matched_instance_hourly_rate.

README HONESTY REQUIREMENT (also stated in docs/README.md):
  VM telemetry is real (Bitbrains GWA-T-12 trace). Cost is a computed
  estimate from a documented instance-matching and pricing-engine
  methodology - not an observed billing invoice.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd

from app.data.instance_specs import INSTANCE_SPECS, InstanceSpec

# Below this confidence, a VM is flagged for manual review instead of
# silently auto-assigned to its nearest (poor) match.
CONFIDENCE_THRESHOLD = 0.55

# Weights for the weighted distance score across CPU and memory dimensions.
CPU_WEIGHT = 0.5
MEMORY_WEIGHT = 0.5

# A candidate family must be within this multiplicative size band of the
# VM's footprint to be considered at all (step 3: "reasonable size range").
SIZE_RANGE_MIN = 0.4
SIZE_RANGE_MAX = 2.5


@dataclass
class MatchResult:
    vm_id: int | str
    matched_instance_type: str | None
    confidence: float
    distance: float
    needs_manual_review: bool
    vm_cpu_cores: int
    vm_ram_gb: float


def _candidate_filter(vm_cpu: float, vm_ram_gb: float, specs: list[InstanceSpec]) -> list[InstanceSpec]:
    """Step 3: filter candidate families to a reasonable size range around the VM's footprint."""
    candidates = []
    for s in specs:
        cpu_ratio = s.vcpu / max(vm_cpu, 0.01)
        ram_ratio = s.ram_gb / max(vm_ram_gb, 0.01)
        if SIZE_RANGE_MIN <= cpu_ratio <= SIZE_RANGE_MAX and SIZE_RANGE_MIN <= ram_ratio <= SIZE_RANGE_MAX:
            candidates.append(s)
    return candidates if candidates else specs  # fall back to all specs if nothing in range


def _weighted_distance(vm_cpu: float, vm_ram_gb: float, spec: InstanceSpec) -> float:
    """Step 4: weighted normalized distance across CPU + memory dimensions."""
    cpu_norm_diff = abs(spec.vcpu - vm_cpu) / max(spec.vcpu, vm_cpu, 1)
    ram_norm_diff = abs(spec.ram_gb - vm_ram_gb) / max(spec.ram_gb, vm_ram_gb, 1)
    return CPU_WEIGHT * cpu_norm_diff + MEMORY_WEIGHT * ram_norm_diff


def match_vm_to_instance_type(
    vm_cpu_cores: float,
    vm_ram_gb: float,
    vm_id: int | str,
    specs: list[InstanceSpec] | None = None,
) -> MatchResult:
    """
    Runs the full deterministic matching pipeline (steps 1-7) for a
    single VM's normalized CPU/memory footprint.
    """
    specs = specs or INSTANCE_SPECS

    # Steps 1-2: normalization happens implicitly inside the distance function -
    # both VM and candidate spec are compared on the same vCPU / RAM_GB units.
    candidates = _candidate_filter(vm_cpu_cores, vm_ram_gb, specs)

    scored = [(s, _weighted_distance(vm_cpu_cores, vm_ram_gb, s)) for s in candidates]
    scored.sort(key=lambda t: t[1])
    best_spec, best_distance = scored[0]

    # Step 6: confidence is an inverse function of distance, bounded [0, 1].
    # distance of 0 -> confidence 1.0; distance grows -> confidence decays.
    confidence = math.exp(-3.0 * best_distance)

    needs_review = confidence < CONFIDENCE_THRESHOLD

    return MatchResult(
        vm_id=vm_id,
        matched_instance_type=None if needs_review else best_spec.instance_type,
        confidence=round(confidence, 4),
        distance=round(best_distance, 4),
        needs_manual_review=needs_review,
        vm_cpu_cores=vm_cpu_cores,
        vm_ram_gb=vm_ram_gb,
    )


def _select_hourly_rate(pricing_df: pd.DataFrame, instance_type: str) -> tuple[float | None, str | None]:
    """
    Picks a representative hourly rate for a matched instance type from the
    pricing silver table. Prefers on_demand pricing (most stable/comparable),
    falls back to spot, then prediction. Returns (rate, pricing_type_used).
    """
    rows = pricing_df[pricing_df["instance_type"].str.lower() == instance_type.lower()]
    if rows.empty:
        return None, None
    for ptype in ["on_demand", "spot", "prediction"]:
        subset = rows[rows["pricing_type"] == ptype]
        if not subset.empty:
            return float(subset["hourly_rate"].mean()), ptype
    return float(rows["hourly_rate"].mean()), "mixed"


def build_gold_dataset(
    silver_telemetry_path: str,
    silver_pricing_path: str,
    gold_dir: str,
    manifest_path: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Joins telemetry + matched instance type + computed cost into one
    ML-ready Gold dataset. Returns (gold_df, manual_review_df).
    """
    os.makedirs(gold_dir, exist_ok=True)
    manifest: dict = {"stage": "gold", "created_at": datetime.now(timezone.utc).isoformat(), "steps": []}

    telemetry = pd.read_csv(silver_telemetry_path, parse_dates=["date"])
    pricing = pd.read_csv(silver_pricing_path)
    manifest["steps"].append({"step": "load_silver", "telemetry_rows": len(telemetry), "pricing_rows": len(pricing)})

    # One match per VM (VM hardware footprint is constant across its history in this trace)
    vm_footprint = telemetry.groupby("VM_ID").agg(
        CPU_Cores=("CPU_Cores", "first"),
        Memory_Provisioned_MB=("Memory_Provisioned_MB", "first"),
    ).reset_index()
    vm_footprint["ram_gb"] = vm_footprint["Memory_Provisioned_MB"] / 1024.0

    match_results = [
        match_vm_to_instance_type(row.CPU_Cores, row.ram_gb, row.VM_ID)
        for row in vm_footprint.itertuples()
    ]
    match_df = pd.DataFrame([vars(m) for m in match_results])
    manifest["steps"].append({
        "step": "instance_matching",
        "vms_matched": int((~match_df["needs_manual_review"]).sum()),
        "vms_flagged_for_review": int(match_df["needs_manual_review"].sum()),
    })

    manual_review_df = match_df[match_df["needs_manual_review"]].copy()

    # Join matched instance type back onto the daily telemetry rows
    merged = telemetry.merge(match_df[["vm_id", "matched_instance_type", "confidence"]],
                              left_on="VM_ID", right_on="vm_id", how="left")

    # Resolve hourly rate per matched instance type from the pricing silver table
    rate_cache: dict[str, tuple[float | None, str | None]] = {}
    rates, rate_sources = [], []
    for itype in merged["matched_instance_type"]:
        if pd.isna(itype):
            rates.append(None)
            rate_sources.append(None)
            continue
        if itype not in rate_cache:
            rate_cache[itype] = _select_hourly_rate(pricing, itype)
        rate, source = rate_cache[itype]
        rates.append(rate)
        rate_sources.append(source)
    merged["matched_hourly_rate"] = rates
    merged["rate_source"] = rate_sources

    # Step 8: daily_cost = usage_hours x matched_instance_hourly_rate.
    # Telemetry here is sampled continuously, so usage_hours = 24 (always-on VM).
    merged["usage_hours"] = 24.0
    merged["cost"] = merged["usage_hours"] * merged["matched_hourly_rate"]

    unpriced = merged["cost"].isna().sum()
    manifest["steps"].append({
        "step": "cost_computation",
        "rows_with_cost": int(merged["cost"].notna().sum()),
        "rows_unpriced_no_rate_match": int(unpriced),
    })

    gold = merged.rename(columns={
        "VM_ID": "resource_id",
        "matched_instance_type": "instance_type",
        "CPU_Usage_Percent": "cpu_avg_pct",
    }).copy()
    gold["memory_avg_pct"] = (gold["Memory_Utilization_Ratio"] * 100).round(2)
    gold["disk_io"] = gold["Disk_Read_KBps"] + gold["Disk_Write_KBps"]
    gold["network_io"] = gold["Network_Received_KBps"] + gold["Network_Transmitted_KBps"]
    gold["service"] = "EC2"
    gold["account_id"] = "bitbrains-prod"
    gold["region"] = None  # Bitbrains trace carries no region info - left null, not fabricated
    # VMs that failed confidence-gated matching keep their row (visible, not dropped)
    # but carry no fabricated cost - they're explicitly flagged for manual pricing.
    gold["needs_manual_pricing"] = gold["instance_type"].isna()

    gold = gold.sort_values(["resource_id", "date"]).reset_index(drop=True)
    gold["runtime_days"] = gold.groupby("resource_id").cumcount() + 1
    growth = gold.groupby("resource_id")["cost"].pct_change(fill_method=None)
    gold["cost_growth_rate"] = growth.fillna(0.0).astype(float)

    keep_cols = [
        "date", "account_id", "service", "resource_id", "instance_type", "region",
        "cost", "usage_hours", "cpu_avg_pct", "memory_avg_pct", "disk_io", "network_io",
        "runtime_days", "cost_growth_rate", "confidence", "rate_source", "needs_manual_pricing",
    ]
    gold = gold[keep_cols]

    gold_path = os.path.join(gold_dir, "gold_bitbrains.csv")
    gold.to_csv(gold_path, index=False)
    review_path = os.path.join(gold_dir, "manual_review_vms.csv")
    manual_review_df.to_csv(review_path, index=False)

    manifest["steps"].append({"step": "write_gold", "gold_rows": len(gold), "manual_review_rows": len(manual_review_df)})

    if manifest_path:
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

    return gold, manual_review_df


if __name__ == "__main__":
    gold, review = build_gold_dataset(
        silver_telemetry_path="app/data/silver/bitbrains_cleaned_v2/bitbrains_daily_silver.csv",
        silver_pricing_path="app/data/silver/pricing_cleaned_v2/pricing_silver.csv",
        gold_dir="app/data/gold/gold_v3",
        manifest_path="app/data/gold/gold_v3/manifest.json",
    )
    print(gold)
    print("\nManual review needed for VMs:")
    print(review)

"""
Part 2 - Feature Engineering.

This module takes any dataframe already shaped like the internal schema
(output of any of the 4 data tiers) and computes the full feature set
described in the spec. It is tier-agnostic: the exact same function
runs on synthetic, Bitbrains, CSV-upload, or future live-AWS data,
which is the whole point of normalizing every tier into one schema
first.

Computed:
  - Utilization ratios (only if the source columns exist - some tiers
    have cpu_avg_pct/memory_avg_pct directly rather than raw MHz/KB)
  - I/O features (total disk I/O, total network I/O)
  - Time-based features (hour, day of week, month, weekend flag)
  - Rolling statistics (7-day, 30-day rolling average cost/cpu/memory)
  - Lag features (cost/cpu/memory 1 day ago, cost 7 days ago)
  - Derived business features (cost per utilization, cost growth rate,
    runtime days, resource age)
"""
from __future__ import annotations

import pandas as pd


def add_time_features(df: pd.DataFrame, date_col: str = "date") -> pd.DataFrame:
    out = df.copy()
    out[date_col] = pd.to_datetime(out[date_col])
    out["hour_of_day"] = out[date_col].dt.hour
    out["day_of_week"] = out[date_col].dt.dayofweek  # 0=Monday
    out["day_of_month"] = out[date_col].dt.day
    out["month"] = out[date_col].dt.month
    out["is_weekend"] = (out["day_of_week"] >= 5).astype(int)
    return out


def add_io_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if {"Disk_Read_KBps", "Disk_Write_KBps"}.issubset(out.columns):
        out["total_disk_io"] = out["Disk_Read_KBps"] + out["Disk_Write_KBps"]
    elif "disk_io" in out.columns:
        out["total_disk_io"] = out["disk_io"]

    if {"Network_Received_KBps", "Network_Transmitted_KBps"}.issubset(out.columns):
        out["total_network_io"] = out["Network_Received_KBps"] + out["Network_Transmitted_KBps"]
    elif "network_io" in out.columns:
        out["total_network_io"] = out["network_io"]
    return out


def add_utilization_ratios(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if {"CPU_Usage_MHz", "CPU_Capacity_MHz"}.issubset(out.columns):
        out["cpu_utilization_ratio"] = (out["CPU_Usage_MHz"] / out["CPU_Capacity_MHz"]).clip(0, 1)
    elif "cpu_avg_pct" in out.columns:
        out["cpu_utilization_ratio"] = (out["cpu_avg_pct"] / 100.0).clip(0, 1)

    if {"Memory_Usage_KB", "Memory_Provisioned_KB"}.issubset(out.columns):
        out["memory_utilization_ratio"] = (out["Memory_Usage_KB"] / out["Memory_Provisioned_KB"]).clip(0, 1)
    elif "memory_avg_pct" in out.columns:
        out["memory_utilization_ratio"] = (out["memory_avg_pct"] / 100.0).clip(0, 1)
    return out


def add_rolling_and_lag_features(df: pd.DataFrame, group_col: str = "resource_id", date_col: str = "date") -> pd.DataFrame:
    out = df.sort_values([group_col, date_col]).copy()
    grouped = out.groupby(group_col)

    if "cost" in out.columns:
        out["rolling_avg_cost_7d"] = grouped["cost"].transform(lambda s: s.rolling(7, min_periods=1).mean())
        out["rolling_avg_cost_30d"] = grouped["cost"].transform(lambda s: s.rolling(30, min_periods=1).mean())
        out["lag_cost_1d"] = grouped["cost"].shift(1)
        out["lag_cost_7d"] = grouped["cost"].shift(7)

    if "cpu_avg_pct" in out.columns:
        out["rolling_avg_cpu_7d"] = grouped["cpu_avg_pct"].transform(lambda s: s.rolling(7, min_periods=1).mean())
        out["rolling_avg_cpu_30d"] = grouped["cpu_avg_pct"].transform(lambda s: s.rolling(30, min_periods=1).mean())
        out["lag_cpu_1d"] = grouped["cpu_avg_pct"].shift(1)

    if "memory_avg_pct" in out.columns:
        out["rolling_avg_memory_7d"] = grouped["memory_avg_pct"].transform(lambda s: s.rolling(7, min_periods=1).mean())
        out["rolling_avg_memory_30d"] = grouped["memory_avg_pct"].transform(lambda s: s.rolling(30, min_periods=1).mean())
        out["lag_memory_1d"] = grouped["memory_avg_pct"].shift(1)

    return out


def add_derived_business_features(df: pd.DataFrame, group_col: str = "resource_id", date_col: str = "date") -> pd.DataFrame:
    out = df.copy()

    if "cost" in out.columns and "cpu_avg_pct" in out.columns:
        # avoid division by zero; treat near-zero utilization as a small floor
        out["cost_per_cpu_utilization"] = out["cost"] / out["cpu_avg_pct"].clip(lower=1.0)
    if "cost" in out.columns and "memory_avg_pct" in out.columns:
        out["cost_per_memory_utilization"] = out["cost"] / out["memory_avg_pct"].clip(lower=1.0)

    if "cost" in out.columns:
        growth = out.groupby(group_col)["cost"].pct_change(fill_method=None)
        out["cost_growth_rate"] = growth.fillna(0.0).astype(float)

    out = out.sort_values([group_col, date_col])
    out["runtime_days"] = out.groupby(group_col).cumcount() + 1

    first_seen = out.groupby(group_col)[date_col].transform("min")
    out["resource_age_days"] = (pd.to_datetime(out[date_col]) - pd.to_datetime(first_seen)).dt.days

    return out


def engineer_features(df: pd.DataFrame, group_col: str = "resource_id", date_col: str = "date") -> pd.DataFrame:
    """Runs the full Part 2 feature engineering pipeline on any internal-schema dataframe."""
    out = df.copy()
    out = add_time_features(out, date_col=date_col)
    out = add_io_features(out)
    out = add_utilization_ratios(out)
    out = add_rolling_and_lag_features(out, group_col=group_col, date_col=date_col)
    out = add_derived_business_features(out, group_col=group_col, date_col=date_col)
    return out


if __name__ == "__main__":
    billing = pd.read_csv("app/data/synthetic/billing_data.csv", parse_dates=["date"])
    featured = engineer_features(billing)
    print("Input columns:", len(billing.columns))
    print("Output columns:", len(featured.columns))
    print("New columns added:", sorted(set(featured.columns) - set(billing.columns)))
    print()
    print(featured.head(3).T)

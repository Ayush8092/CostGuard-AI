"""
Tier 1 - Synthetic data generator (Part 1).

Generates realistic-looking multi-account cloud billing data with a
known ground truth: every injected anomaly is logged to
ground_truth_anomalies.csv with its exact dates and resource id. That
file is used ONLY for evaluating the anomaly/waste models afterward -
it is never fed into feature engineering or training.

Run directly:
    python -m app.data.generate_data
"""
from __future__ import annotations

import os
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

random.seed(42)
np.random.seed(42)

ACCOUNTS = ["dev", "test", "prod"]
SERVICES = ["EC2", "S3", "RDS", "Lambda"]
REGIONS = ["us-east-1", "us-west-2", "ap-south-1", "eu-west-1"]
INSTANCE_TYPES = {
    "EC2": ["t3.micro", "t3.medium", "m5.large", "m5.xlarge", "c5.large", "c5.xlarge", "r4.xlarge"],
    "RDS": ["db.t3.medium", "db.m5.large", "db.r5.large"],
    "S3": [None],
    "Lambda": [None],
}

# base hourly-equivalent daily cost per instance family, used to seed realistic spend
BASE_DAILY_COST = {
    "t3.micro": 0.30, "t3.medium": 1.00, "m5.large": 2.30, "m5.xlarge": 4.60,
    "c5.large": 2.04, "c5.xlarge": 4.08, "r4.xlarge": 3.21,
    "db.t3.medium": 1.50, "db.m5.large": 3.60, "db.r5.large": 6.00,
}


@dataclass
class Resource:
    resource_id: str
    account_id: str
    service: str
    instance_type: str | None
    region: str
    base_cost: float
    base_cpu: float
    base_mem: float
    start_offset_days: int  # how many days into the window the resource appears


@dataclass
class AnomalyEvent:
    resource_id: str
    anomaly_type: str  # idle_but_billed | spend_spike | slow_leak
    start_date: str
    end_date: str
    detail: str


def _make_resources(n_resources: int) -> list[Resource]:
    resources = []
    for i in range(n_resources):
        account = ACCOUNTS[i % len(ACCOUNTS)]
        service = random.choice(SERVICES)
        instance_type = random.choice(INSTANCE_TYPES[service])
        region = random.choice(REGIONS)
        if instance_type and instance_type in BASE_DAILY_COST:
            base_cost = BASE_DAILY_COST[instance_type]
        else:
            # S3/Lambda: usage-based, smaller baseline with more variance
            base_cost = round(random.uniform(0.5, 5.0), 2)
        resources.append(
            Resource(
                resource_id=f"{service.lower()}-{account}-{i:03d}",
                account_id=account,
                service=service,
                instance_type=instance_type,
                region=region,
                base_cost=base_cost,
                # Wider, more realistic spread of resource health profiles:
                # roughly a third of the fleet runs genuinely well-utilized
                # (Healthy candidates), a third sits in the moderate band
                # used previously, and a chunk runs chronically low (good
                # Critical Waste / Idle candidates even before any anomaly
                # injection) - mirrors a real, heterogeneous fleet rather
                # than a fleet that's uniformly "medium".
                base_cpu=random.choice([
                    random.uniform(55, 80),   # well-utilized
                    random.uniform(20, 55),   # moderate (previous range)
                    random.uniform(1, 12),    # chronically idle
                ]),
                base_mem=random.choice([
                    random.uniform(55, 80),
                    random.uniform(25, 55),
                    random.uniform(5, 20),
                ]),
                start_offset_days=random.choice([0, 0, 0, 30, 60]),  # most exist from day 1
            )
        )
    return resources


def _daily_series(n_days: int, base: float, trend_pct_per_month: float, weekly_amp: float,
                   monthly_amp: float, noise_std: float, floor: float = 0.0) -> np.ndarray:
    days = np.arange(n_days)
    trend = base * (1 + trend_pct_per_month / 30 / 100) ** days
    weekly = 1 + weekly_amp * np.sin(2 * np.pi * days / 7)
    monthly = 1 + monthly_amp * np.sin(2 * np.pi * days / 30)
    noise = np.random.normal(0, noise_std, n_days)
    series = trend * weekly * monthly + noise
    return np.maximum(series, floor)


def generate(
    n_days: int = 300,
    n_resources: int = 20,
    n_anomalies: int = 20,
    output_dir: str = "app/data/synthetic",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    os.makedirs(output_dir, exist_ok=True)

    start_date = datetime.today() - timedelta(days=n_days)
    resources = _make_resources(n_resources)

    rows = []
    anomaly_events: list[AnomalyEvent] = []

    # decide which resources get which anomaly type, spread across the fleet
    anomaly_targets = random.sample(resources, min(n_anomalies, len(resources)))
    anomaly_types_cycle = (["idle_but_billed", "spend_spike", "slow_leak"] * n_anomalies)[:len(anomaly_targets)]

    anomaly_plan: dict[str, list[tuple[str, int, int]]] = {}  # resource_id -> [(type, start_day, length)]
    for res, atype in zip(anomaly_targets, anomaly_types_cycle):
        if atype == "idle_but_billed":
            length = random.randint(7, 14)
        elif atype == "spend_spike":
            length = random.randint(1, 3)
        else:  # slow_leak
            length = random.randint(14, 30)
        start_day = random.randint(20, n_days - length - 5)
        anomaly_plan.setdefault(res.resource_id, []).append((atype, start_day, length))

    for res in resources:
        cpu_series = _daily_series(n_days, res.base_cpu, trend_pct_per_month=0.5,
                                    weekly_amp=0.05, monthly_amp=0.02, noise_std=3.0, floor=1.0)
        mem_series = _daily_series(n_days, res.base_mem, trend_pct_per_month=0.3,
                                    weekly_amp=0.03, monthly_amp=0.02, noise_std=2.5, floor=1.0)
        cost_series = _daily_series(n_days, res.base_cost, trend_pct_per_month=1.2,
                                     weekly_amp=0.15, monthly_amp=0.08, noise_std=res.base_cost * 0.08,
                                     floor=res.base_cost * 0.1)

        # apply this resource's planned anomalies on top of its normal series
        for atype, start_day, length in anomaly_plan.get(res.resource_id, []):
            end_day = min(start_day + length, n_days - 1)
            if atype == "idle_but_billed":
                cpu_series[start_day:end_day] = np.random.uniform(0.5, 5.0, end_day - start_day)
                mem_series[start_day:end_day] = np.random.uniform(2.0, 8.0, end_day - start_day)
                # cost stays roughly flat/unchanged - billed despite no usage
            elif atype == "spend_spike":
                multiplier = random.uniform(2.0, 4.0)
                cost_series[start_day:end_day] *= multiplier
                cpu_series[start_day:end_day] = np.minimum(cpu_series[start_day:end_day] * 1.5, 95)
            else:  # slow_leak
                creep = np.linspace(1.0, 1 + random.uniform(0.3, 0.6), end_day - start_day)
                cost_series[start_day:end_day] *= creep

            anomaly_events.append(
                AnomalyEvent(
                    resource_id=res.resource_id,
                    anomaly_type=atype,
                    start_date=(start_date + timedelta(days=int(start_day))).strftime("%Y-%m-%d"),
                    end_date=(start_date + timedelta(days=int(end_day))).strftime("%Y-%m-%d"),
                    detail=f"{atype} injected for {end_day - start_day} days",
                )
            )

        for d in range(res.start_offset_days, n_days):
            current_date = start_date + timedelta(days=d)
            usage_hours = 24.0 if res.instance_type else round(random.uniform(0.5, 24.0), 2)
            rows.append(
                {
                    "date": current_date.strftime("%Y-%m-%d"),
                    "account_id": res.account_id,
                    "service": res.service,
                    "resource_id": res.resource_id,
                    "instance_type": res.instance_type,
                    "region": res.region,
                    "cost": round(float(cost_series[d]), 4),
                    "usage_hours": usage_hours,
                    "cpu_avg_pct": round(float(np.clip(cpu_series[d], 0, 100)), 2),
                    "memory_avg_pct": round(float(np.clip(mem_series[d], 0, 100)), 2),
                    "disk_io": round(float(np.random.uniform(10, 500)), 2),
                    "network_io": round(float(np.random.uniform(5, 300)), 2),
                }
            )

    billing_df = pd.DataFrame(rows).sort_values(["resource_id", "date"]).reset_index(drop=True)

    # derived fields per the internal schema: runtime_days, cost_growth_rate, anomaly_history_count
    billing_df["date"] = pd.to_datetime(billing_df["date"])
    billing_df["runtime_days"] = billing_df.groupby("resource_id").cumcount() + 1
    billing_df["cost_growth_rate"] = (
        billing_df.groupby("resource_id")["cost"].pct_change(fill_method=None).fillna(0.0)
    )

    anomalies_df = pd.DataFrame([vars(a) for a in anomaly_events])

    anomaly_counts = anomalies_df.groupby("resource_id").size().to_dict() if not anomalies_df.empty else {}
    billing_df["anomaly_history_count"] = billing_df["resource_id"].map(anomaly_counts).fillna(0).astype(int)

    # waste labels: a simple ground-truth bucket derived independently, for waste-model evaluation only
    last_30 = billing_df[billing_df["date"] >= billing_df["date"].max() - timedelta(days=30)]
    waste_rows = []
    for rid, grp in last_30.groupby("resource_id"):
        avg_cpu = grp["cpu_avg_pct"].mean()
        avg_mem = grp["memory_avg_pct"].mean()
        if avg_cpu < 5:
            bucket = "Critical Waste"
        elif avg_cpu < 20:
            bucket = "Idle"
        elif avg_cpu < 40:
            bucket = "Underutilized"
        else:
            bucket = "Healthy"
        waste_rows.append({"resource_id": rid, "avg_cpu_pct": round(avg_cpu, 2),
                            "avg_memory_pct": round(avg_mem, 2), "waste_label": bucket})
    waste_df = pd.DataFrame(waste_rows)

    billing_df.to_csv(os.path.join(output_dir, "billing_data.csv"), index=False)
    anomalies_df.to_csv(os.path.join(output_dir, "ground_truth_anomalies.csv"), index=False)
    waste_df.to_csv(os.path.join(output_dir, "waste_labels.csv"), index=False)

    return billing_df, anomalies_df, waste_df


if __name__ == "__main__":
    billing, anomalies, waste = generate(n_days=365, n_resources=32, n_anomalies=24)
    print(f"billing_data.csv: {len(billing)} rows")
    print(f"ground_truth_anomalies.csv: {len(anomalies)} rows")
    print(f"waste_labels.csv: {len(waste)} rows")
    print(billing.head())
    print()
    print("Anomaly type distribution:")
    print(anomalies["anomaly_type"].value_counts())
    print()
    print("Date range:", billing["date"].min(), "to", billing["date"].max())
    print("Resources:", billing["resource_id"].nunique())
    print("Accounts:", billing["account_id"].unique().tolist())

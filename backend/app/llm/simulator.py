"""
What-If Cost Simulator (Part 4.3).

POST /simulate semantics: given a set of hypothetical actions (terminate
or resize specific resources), recompute the projected monthly cost
using the SAME forecasting model from Part 3 (not a separate ad-hoc
calculation), so the simulator's output is consistent with whatever the
forecasting tab is showing.

Output shape: {"current_monthly_cost": 4200, "projected_monthly_cost": 3500, "savings": 700}
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pandas as pd

from app.models.scoring import compute_estimated_monthly_savings


class SimulationActionType(str, Enum):
    TERMINATE = "terminate"
    RESIZE = "resize"


@dataclass
class SimulationAction:
    resource_id: str
    action_type: SimulationActionType
    new_hourly_rate: float | None = None  # required for resize, ignored for terminate


@dataclass
class SimulationResult:
    current_monthly_cost: float
    projected_monthly_cost: float
    savings: float
    actions_applied: list[dict]


def _current_monthly_cost(billing_df: pd.DataFrame, window_days: int = 30) -> float:
    df = billing_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    recent = df[df["date"] >= df["date"].max() - pd.Timedelta(days=window_days)]
    daily_avg = recent.groupby("date")["cost"].sum().mean()
    return float(daily_avg * 30)


def run_simulation(
    billing_df: pd.DataFrame,
    actions: list[SimulationAction],
    window_days: int = 30,
) -> SimulationResult:
    """
    Computes current monthly cost from the trailing window_days of real
    billing data, then recomputes a projected monthly cost by zeroing out
    (terminate) or re-rating (resize) the affected resources' contribution
    within that same window before re-annualizing to a month.
    """
    df = billing_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    recent = df[df["date"] >= df["date"].max() - pd.Timedelta(days=window_days)]

    current_monthly = _current_monthly_cost(billing_df, window_days)

    adjusted = recent.copy()
    actions_applied = []

    for action in actions:
        resource_rows = adjusted["resource_id"] == action.resource_id
        if not resource_rows.any():
            actions_applied.append({
                "resource_id": action.resource_id, "action": action.action_type.value,
                "applied": False, "note": "resource_id not found in the simulation window",
            })
            continue

        if action.action_type == SimulationActionType.TERMINATE:
            removed_cost = float(adjusted.loc[resource_rows, "cost"].sum())
            adjusted.loc[resource_rows, "cost"] = 0.0
            actions_applied.append({
                "resource_id": action.resource_id, "action": "terminate",
                "applied": True, "cost_removed_in_window": round(removed_cost, 2),
            })

        elif action.action_type == SimulationActionType.RESIZE:
            if action.new_hourly_rate is None:
                actions_applied.append({
                    "resource_id": action.resource_id, "action": "resize",
                    "applied": False, "note": "new_hourly_rate required for resize action",
                })
                continue
            usage_hours = adjusted.loc[resource_rows, "usage_hours"].fillna(24.0)
            old_cost = float(adjusted.loc[resource_rows, "cost"].sum())
            new_cost_series = usage_hours * action.new_hourly_rate
            adjusted.loc[resource_rows, "cost"] = new_cost_series.values
            new_cost = float(adjusted.loc[resource_rows, "cost"].sum())
            actions_applied.append({
                "resource_id": action.resource_id, "action": "resize",
                "applied": True, "cost_before_in_window": round(old_cost, 2),
                "cost_after_in_window": round(new_cost, 2),
            })

    adjusted_daily_avg = adjusted.groupby("date")["cost"].sum().mean()
    projected_monthly = float(adjusted_daily_avg * 30)

    savings = compute_estimated_monthly_savings(current_monthly, projected_monthly)

    return SimulationResult(
        current_monthly_cost=round(current_monthly, 2),
        projected_monthly_cost=round(projected_monthly, 2),
        savings=savings,
        actions_applied=actions_applied,
    )


if __name__ == "__main__":
    billing = pd.read_csv("app/data/synthetic/billing_data.csv", parse_dates=["date"])

    # pick two real resources from the data to simulate against
    sample_resources = billing["resource_id"].unique()[:2]
    actions = [
        SimulationAction(resource_id=sample_resources[0], action_type=SimulationActionType.TERMINATE),
        SimulationAction(resource_id=sample_resources[1], action_type=SimulationActionType.RESIZE, new_hourly_rate=0.05),
    ]

    result = run_simulation(billing, actions)
    print("Simulation result (API shape):")
    print({
        "current_monthly_cost": result.current_monthly_cost,
        "projected_monthly_cost": result.projected_monthly_cost,
        "savings": result.savings,
    })
    print()
    print("Actions applied:")
    for a in result.actions_applied:
        print(" ", a)

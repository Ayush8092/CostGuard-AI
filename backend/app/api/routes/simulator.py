"""
Simulator route (Part 9, Tab 5 / Part 4.3).

Unlike dashboard/forecast/recommendation reads, the simulator is
explicitly interactive ("what if I terminate X") and must respond to
the user's exact hypothetical in real time - this is the one synchronous
compute-on-request path the spec carves out deliberately ("Async scoped
correctly: task-queue pattern only for expensive operations... dashboard/
forecast/recommendation reads stay synchronous fast cached reads" - the
simulator is also synchronous, but because its computation is cheap
(in-memory pandas aggregation over one org's recent window), not because
results are cached).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.db.models import ProcessedTelemetry
from app.db.session import get_db
from app.llm.simulator import SimulationAction, SimulationActionType, run_simulation

router = APIRouter(prefix="/simulate", tags=["simulator"])


class SimulationActionIn(BaseModel):
    resource_id: str
    action_type: str  # "terminate" | "resize"
    new_hourly_rate: float | None = None


class SimulationRequest(BaseModel):
    actions: list[SimulationActionIn]
    window_days: int = 30


class SimulationResponseOut(BaseModel):
    current_monthly_cost: float
    projected_monthly_cost: float
    savings: float
    actions_applied: list[dict]


@router.post("", response_model=SimulationResponseOut)
def simulate(
    payload: SimulationRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SimulationResponseOut:
    rows = db.query(ProcessedTelemetry).filter(
        ProcessedTelemetry.organization_id == current_user.organization_id,
    ).all()
    if not rows:
        raise HTTPException(status_code=404, detail="No billing data available for this organization yet")

    import pandas as pd
    billing_df = pd.DataFrame([{
        "date": r.date, "resource_id": r.resource_id, "cost": r.cost, "usage_hours": r.usage_hours,
    } for r in rows])

    actions = [
        SimulationAction(
            resource_id=a.resource_id,
            action_type=SimulationActionType(a.action_type),
            new_hourly_rate=a.new_hourly_rate,
        )
        for a in payload.actions
    ]

    result = run_simulation(billing_df, actions, window_days=payload.window_days)
    return SimulationResponseOut(
        current_monthly_cost=result.current_monthly_cost,
        projected_monthly_cost=result.projected_monthly_cost,
        savings=result.savings,
        actions_applied=result.actions_applied,
    )

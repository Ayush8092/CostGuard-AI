"""
AI Weekly Executive Report (Part 4.4).

GET /reports/weekly - pulls last 7 days of REAL metrics from billing
data, the waste classifier, and the anomaly detector, then has the LLM
fill a fixed template narrating only those numbers. The metrics_snapshot
assembled here is exactly what gets persisted to the weekly_reports
table (Part 7) alongside the narrative, so the narrative can always be
audited against the real numbers that produced it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pandas as pd

from app.llm.client import LlmClient

REPORT_SYSTEM_PROMPT = (
    "You are writing a concise weekly FinOps executive report. You will be given a "
    "JSON snapshot of real metrics for the past 7 days. Write 3-5 short paragraphs "
    "covering: (1) total spend and how it compares to the prior week, (2) the "
    "anomalies/incidents detected, (3) the waste/optimization picture, (4) a brief "
    "outlook. ONLY reference numbers that appear in the provided JSON snapshot. Do "
    "not invent any figure, percentage, or resource name that is not present in the "
    "snapshot. Keep the tone professional and direct, suitable for a CTO or VP of "
    "Engineering audience."
)


def build_weekly_metrics_snapshot(
    billing_df: pd.DataFrame,
    waste_scored_df: pd.DataFrame | None = None,
    anomalies_df: pd.DataFrame | None = None,
    recommendations_summary: dict | None = None,
) -> dict:
    """
    Assembles the real metrics_snapshot for the last 7 vs prior 7 days.
    This is the ONLY source of numbers the LLM is allowed to use - every
    figure in the eventual narrative must trace back to this dict.
    """
    df = billing_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    period_end = df["date"].max()
    period_start = period_end - timedelta(days=7)
    prior_start = period_start - timedelta(days=7)

    this_week = df[(df["date"] > period_start) & (df["date"] <= period_end)]
    prior_week = df[(df["date"] > prior_start) & (df["date"] <= period_start)]

    this_week_total = round(float(this_week["cost"].sum()), 2)
    prior_week_total = round(float(prior_week["cost"].sum()), 2)
    pct_change = round((this_week_total / max(prior_week_total, 1e-6) - 1) * 100, 2)

    by_service = this_week.groupby("service")["cost"].sum().sort_values(ascending=False)
    top_services = {k: round(float(v), 2) for k, v in by_service.head(3).items()}

    snapshot: dict = {
        "period_start": period_start.strftime("%Y-%m-%d"),
        "period_end": period_end.strftime("%Y-%m-%d"),
        "this_week_total_cost": this_week_total,
        "prior_week_total_cost": prior_week_total,
        "pct_change_vs_prior_week": pct_change,
        "top_services_by_cost": top_services,
        "active_resource_count": int(this_week["resource_id"].nunique()),
    }

    if waste_scored_df is not None:
        recent_waste = waste_scored_df[waste_scored_df["date"] > period_start] if "date" in waste_scored_df.columns else waste_scored_df
        bucket_counts = recent_waste["bucket"].value_counts().to_dict() if "bucket" in recent_waste.columns else {}
        snapshot["waste_bucket_counts"] = {k: int(v) for k, v in bucket_counts.items()}

    if anomalies_df is not None and "date" in anomalies_df.columns:
        recent_anomalies = anomalies_df[pd.to_datetime(anomalies_df["date"]) > period_start]
        snapshot["anomaly_count_this_week"] = int(len(recent_anomalies))
        if "severity" in recent_anomalies.columns:
            snapshot["anomalies_by_severity"] = recent_anomalies["severity"].value_counts().to_dict()

    if recommendations_summary:
        snapshot["recommendations_summary"] = recommendations_summary

    return snapshot


def generate_weekly_report(
    billing_df: pd.DataFrame,
    waste_scored_df: pd.DataFrame | None = None,
    anomalies_df: pd.DataFrame | None = None,
    recommendations_summary: dict | None = None,
    llm_client: LlmClient | None = None,
) -> dict:
    """Returns {"metrics_snapshot": ..., "narrative": ..., "is_stub": bool} ready to persist to weekly_reports."""
    snapshot = build_weekly_metrics_snapshot(billing_df, waste_scored_df, anomalies_df, recommendations_summary)

    llm = llm_client or LlmClient()
    user_prompt = (
        "Here is this week's real metrics snapshot. Write the executive report.\n\n"
        + str(snapshot)
    )
    response = llm.complete(system_prompt=REPORT_SYSTEM_PROMPT, user_prompt=user_prompt, max_tokens=600)

    return {
        "period_start": snapshot["period_start"],
        "period_end": snapshot["period_end"],
        "metrics_snapshot": snapshot,
        "narrative": response.text,
        "is_stub": response.is_stub,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    from app.models.waste_classification import train_waste_classifier
    from app.models.anomaly_detection import detect_anomalies

    billing = pd.read_csv("app/data/synthetic/billing_data.csv", parse_dates=["date"])
    _, _, waste_scored = train_waste_classifier(billing)
    anomaly_result = detect_anomalies(billing)

    report = generate_weekly_report(billing, waste_scored_df=waste_scored, anomalies_df=anomaly_result.df)

    print("Metrics snapshot (the ONLY source of truth for numbers in the narrative):")
    for k, v in report["metrics_snapshot"].items():
        print(f"  {k}: {v}")
    print()
    print("Narrative (is_stub =", report["is_stub"], "):")
    print(report["narrative"])

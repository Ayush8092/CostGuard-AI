"""
Scoring Functions (Part 3 / Part 4 / business metrics layer).

EVERYTHING IN THIS FILE IS A FORMULA, NOT A TRAINED MODEL. Per spec Part
10: "No labeling formulas as 'models' - Risk Score, Incident Score, and
Recommendation Ranking are scoring functions, label them as such in
code comments and docs." This file is the single home for every such
formula in the project, so that labeling is unambiguous and auditable
in one place.

Covers:
  - FinOps Risk Score (per organization, 0-100)
  - Recommendation savings formula
  - Composite recommendation confidence formula
  - Recommendation Ranking (impact_score)
  - The business/resume metrics requested on top of the spec:
      1. Estimated Monthly Cost Savings
      2. Waste Detection Coverage
      3. Forecast Error Reduction (already on ForecastEvaluation, re-exposed here)
      4. Optimization Opportunity Rate
      5. Recommendation Confidence (average)
      Bonus: Idle Resource Reduction Potential, Infrastructure Health
      Score, Cost Efficiency Score, Average Prediction Latency
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


def _normalize(value: float, lo: float, hi: float) -> float:
    """Clamps and min-max normalizes a value into [0, 1]. Guards against a zero-width range."""
    if hi - lo < 1e-9:
        return 0.0
    return float(np.clip((value - lo) / (hi - lo), 0, 1))


# ---------------------------------------------------------------------------
# FinOps Risk Score (Part 3) - scoring FUNCTION, not a model.
# risk_score = (0.4 * normalized_forecast_growth + 0.3 * normalized_waste_ratio
#               + 0.3 * normalized_anomaly_count) * 100
# ---------------------------------------------------------------------------
def compute_risk_score(
    forecast_growth_pct: float,
    waste_ratio_pct: float,
    anomaly_count: int,
    forecast_growth_norm_range: tuple[float, float] = (-20.0, 50.0),
    waste_ratio_norm_range: tuple[float, float] = (0.0, 100.0),
    anomaly_count_norm_range: tuple[float, float] = (0.0, 50.0),
) -> dict:
    norm_growth = _normalize(forecast_growth_pct, *forecast_growth_norm_range)
    norm_waste = _normalize(waste_ratio_pct, *waste_ratio_norm_range)
    norm_anomaly = _normalize(anomaly_count, *anomaly_count_norm_range)

    risk_score = (0.4 * norm_growth + 0.3 * norm_waste + 0.3 * norm_anomaly) * 100
    return {
        "risk_score": round(risk_score, 2),
        "components": {
            "normalized_forecast_growth": round(norm_growth, 4),
            "normalized_waste_ratio": round(norm_waste, 4),
            "normalized_anomaly_count": round(norm_anomaly, 4),
        },
        "inputs": {
            "forecast_growth_pct": forecast_growth_pct,
            "waste_ratio_pct": waste_ratio_pct,
            "anomaly_count": anomaly_count,
        },
    }


# ---------------------------------------------------------------------------
# Part 4.2 - Recommendation savings + composite confidence formulas
# ---------------------------------------------------------------------------
def compute_recommendation_savings(current_hourly_rate: float, recommended_hourly_rate: float, projected_runtime_hours: float) -> float:
    """Savings = (current_hourly_rate - recommended_hourly_rate) x projected_runtime."""
    return round(max(0.0, (current_hourly_rate - recommended_hourly_rate) * projected_runtime_hours), 2)


def compute_composite_confidence(
    classifier_confidence: float,   # predict_proba, 0-1
    anomaly_score: float,           # normalized distance from threshold, 0-100 incident_score scale -> rescale to 0-1
    forecast_uncertainty: float,    # width of the CI, smaller = more confident; pass as 0-1 already normalized
    data_quality_score: float,      # from Part 1 validation step, 0-1
    weights: dict[str, float] | None = None,
) -> float:
    """
    confidence = weighted_combination(classifier_confidence, anomaly_score,
                                       forecast_uncertainty, data_quality_score)
    Explicitly NOT classifier probability alone, per spec. forecast_uncertainty
    is expected pre-inverted (1 - normalized_CI_width) so that higher is
    always "more confident" across all four inputs, keeping the weighted
    sum semantically consistent.
    """
    w = weights or {"classifier": 0.35, "anomaly": 0.20, "forecast": 0.20, "data_quality": 0.25}
    anomaly_score_norm = np.clip(anomaly_score / 100.0, 0, 1)
    confidence = (
        w["classifier"] * np.clip(classifier_confidence, 0, 1)
        + w["anomaly"] * anomaly_score_norm
        + w["forecast"] * np.clip(forecast_uncertainty, 0, 1)
        + w["data_quality"] * np.clip(data_quality_score, 0, 1)
    )
    return round(float(confidence * 100), 2)  # report on a 0-100 scale, matching other scores in the project


# ---------------------------------------------------------------------------
# Part 4.6 - Recommendation Ranking. Explicitly a SCORING FUNCTION.
# impact_score = estimated_monthly_savings * confidence_weight
# ---------------------------------------------------------------------------
def compute_impact_score(estimated_monthly_savings: float, confidence_pct: float) -> float:
    confidence_weight = confidence_pct / 100.0
    return round(estimated_monthly_savings * confidence_weight, 2)


def bucket_impact_tier(impact_score: float, high_threshold: float, medium_threshold: float) -> str:
    """High/Medium/Low impact tiers per Part 4.5 (Optimization Planner - pure presentation layer)."""
    if impact_score >= high_threshold:
        return "High"
    if impact_score >= medium_threshold:
        return "Medium"
    return "Low"


# ---------------------------------------------------------------------------
# BUSINESS / RESUME METRICS - all derived from the real model/recommendation
# outputs above, never independently invented numbers.
# ---------------------------------------------------------------------------
@dataclass
class BusinessMetricsSnapshot:
    estimated_monthly_savings: float
    current_monthly_cost: float
    projected_monthly_cost: float
    waste_detection_coverage_pct: float
    forecast_error_reduction_pct: float
    optimization_opportunity_rate_pct: float
    avg_recommendation_confidence_pct: float
    idle_resource_reduction_potential_pct: float
    infrastructure_health_score: float
    cost_efficiency_score: float

    def to_dict(self) -> dict:
        return {
            "estimated_monthly_savings": self.estimated_monthly_savings,
            "current_monthly_cost": self.current_monthly_cost,
            "projected_monthly_cost": self.projected_monthly_cost,
            "waste_detection_coverage_pct": self.waste_detection_coverage_pct,
            "forecast_error_reduction_pct": self.forecast_error_reduction_pct,
            "optimization_opportunity_rate_pct": self.optimization_opportunity_rate_pct,
            "avg_recommendation_confidence_pct": self.avg_recommendation_confidence_pct,
            "idle_resource_reduction_potential_pct": self.idle_resource_reduction_potential_pct,
            "infrastructure_health_score": self.infrastructure_health_score,
            "cost_efficiency_score": self.cost_efficiency_score,
        }


def compute_estimated_monthly_savings(current_monthly_cost: float, projected_monthly_cost: float) -> float:
    """Metric 1 (most important): Savings = Current Monthly Cost - Projected Monthly Cost."""
    return round(current_monthly_cost - projected_monthly_cost, 2)


def compute_waste_detection_coverage(resources_with_recommendation: int, total_waste_resources_detected: int) -> float:
    """Metric 2: coverage = resources_with_recommendation / total_waste_resources_detected, as a percentage."""
    if total_waste_resources_detected == 0:
        return 0.0
    return round(resources_with_recommendation / total_waste_resources_detected * 100, 2)


def compute_optimization_opportunity_rate(resources_needing_optimization: int, total_resources: int) -> float:
    """Metric 4: rate = resources_needing_optimization / total_resources, as a percentage."""
    if total_resources == 0:
        return 0.0
    return round(resources_needing_optimization / total_resources * 100, 2)


def compute_idle_resource_reduction_potential(idle_resources: int, recommended_for_termination: int) -> float:
    """Bonus metric: what fraction of currently idle resources have a termination recommendation."""
    if idle_resources == 0:
        return 0.0
    return round(recommended_for_termination / idle_resources * 100, 2)


def compute_infrastructure_health_score(
    forecast_growth_pct: float,
    waste_ratio_pct: float,
    anomaly_count: int,
    **risk_score_kwargs,
) -> float:
    """
    Bonus metric: Health Score = 100 - risk_score. Deliberately reuses the
    Risk Score formula above rather than inventing a second, inconsistent
    formula - "100 minus risk" is the most defensible inverse framing for
    a dashboard that wants to show "health" trending up as good.
    """
    risk = compute_risk_score(forecast_growth_pct, waste_ratio_pct, anomaly_count, **risk_score_kwargs)
    return round(100 - risk["risk_score"], 2)


def compute_cost_efficiency_score(useful_cpu_hours: float, total_cloud_cost: float) -> float:
    """
    Bonus metric: Cost Efficiency = Useful CPU / Cloud Cost. "Useful CPU"
    here means CPU-hours actually consumed (avg_cpu_pct/100 * hours), so
    this rewards both right-sizing AND genuine utilization, not just low
    spend. Higher = better. Caller supplies the numerator/denominator
    already computed from real telemetry - this function only applies
    the ratio, it does not estimate "useful" on its own.
    """
    if total_cloud_cost <= 0:
        return 0.0
    return round(useful_cpu_hours / total_cloud_cost, 4)


def build_business_metrics_snapshot(
    current_monthly_cost: float,
    projected_monthly_cost: float,
    resources_with_recommendation: int,
    total_waste_resources_detected: int,
    forecast_error_reduction_pct: float,
    resources_needing_optimization: int,
    total_resources: int,
    recommendation_confidences: list[float],
    idle_resources: int,
    recommended_for_termination: int,
    risk_score_inputs: dict,
    useful_cpu_hours: float,
) -> BusinessMetricsSnapshot:
    """Assembles every requested business metric from real upstream numbers in one call."""
    avg_confidence = round(float(np.mean(recommendation_confidences)), 2) if recommendation_confidences else 0.0

    return BusinessMetricsSnapshot(
        estimated_monthly_savings=compute_estimated_monthly_savings(current_monthly_cost, projected_monthly_cost),
        current_monthly_cost=round(current_monthly_cost, 2),
        projected_monthly_cost=round(projected_monthly_cost, 2),
        waste_detection_coverage_pct=compute_waste_detection_coverage(resources_with_recommendation, total_waste_resources_detected),
        forecast_error_reduction_pct=round(forecast_error_reduction_pct, 2),
        optimization_opportunity_rate_pct=compute_optimization_opportunity_rate(resources_needing_optimization, total_resources),
        avg_recommendation_confidence_pct=avg_confidence,
        idle_resource_reduction_potential_pct=compute_idle_resource_reduction_potential(idle_resources, recommended_for_termination),
        infrastructure_health_score=compute_infrastructure_health_score(**risk_score_inputs),
        cost_efficiency_score=compute_cost_efficiency_score(useful_cpu_hours, current_monthly_cost),
    )


if __name__ == "__main__":
    # Demonstration with realistic numbers, matching the spec's own examples.
    risk = compute_risk_score(forecast_growth_pct=12.0, waste_ratio_pct=31.0, anomaly_count=14)
    print("Risk score:", risk)

    savings = compute_recommendation_savings(current_hourly_rate=0.192, recommended_hourly_rate=0.096, projected_runtime_hours=720)
    print("Recommendation savings ($/month for one resized resource):", savings)

    confidence = compute_composite_confidence(
        classifier_confidence=0.95, anomaly_score=82, forecast_uncertainty=0.88, data_quality_score=0.97
    )
    print("Composite confidence:", confidence)

    impact = compute_impact_score(estimated_monthly_savings=savings, confidence_pct=confidence)
    tier = bucket_impact_tier(impact, high_threshold=100, medium_threshold=30)
    print(f"Impact score: {impact}, tier: {tier}")

    print()
    snapshot = build_business_metrics_snapshot(
        current_monthly_cost=12400, projected_monthly_cost=10180,
        resources_with_recommendation=59, total_waste_resources_detected=62,
        forecast_error_reduction_pct=60.0,
        resources_needing_optimization=38, total_resources=120,
        recommendation_confidences=[95, 88, 92, 90, 97],
        idle_resources=43, recommended_for_termination=40,
        risk_score_inputs={"forecast_growth_pct": 12.0, "waste_ratio_pct": 31.0, "anomaly_count": 14},
        useful_cpu_hours=3200,
    )
    print("Business metrics snapshot:")
    for k, v in snapshot.to_dict().items():
        print(f"  {k}: {v}")

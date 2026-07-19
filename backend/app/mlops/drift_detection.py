"""
MLOps - Drift Detection (Part 6).

PSI (Population Stability Index): Sigma((new% - train%) * ln(new% / train%))
  > 0.2 = significant drift

KS statistic (Kolmogorov-Smirnov, scipy.stats.ks_2samp):
  p < 0.05 = drift

Explicit retraining policy - retraining triggers when ANY of:
  - PSI > 0.2 on a key feature, OR
  - forecast MAPE increases >15% from baseline, OR
  - weekly schedule elapsed, OR
  - manual trigger via API
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy import stats

from app.core.config import get_settings

settings = get_settings()


@dataclass
class DriftResult:
    feature: str
    psi: float
    psi_drift_detected: bool
    ks_statistic: float
    ks_pvalue: float
    ks_drift_detected: bool


def compute_psi(train_values: np.ndarray, new_values: np.ndarray, n_bins: int = 10) -> float:
    """
    PSI = sum((new% - train%) * ln(new% / train%)) across n_bins,
    where bins are defined by the TRAINING distribution's quantiles
    (standard PSI methodology - using training quantiles as the fixed
    reference avoids the new distribution's own range from biasing bin
    edges).
    """
    train_values = train_values[~np.isnan(train_values)]
    new_values = new_values[~np.isnan(new_values)]
    if len(train_values) == 0 or len(new_values) == 0:
        return 0.0

    quantiles = np.linspace(0, 1, n_bins + 1)
    bin_edges = np.unique(np.quantile(train_values, quantiles))
    if len(bin_edges) < 3:
        return 0.0  # not enough distinct values to bin meaningfully

    train_counts, _ = np.histogram(train_values, bins=bin_edges)
    new_counts, _ = np.histogram(new_values, bins=bin_edges)

    train_pct = train_counts / max(train_counts.sum(), 1)
    new_pct = new_counts / max(new_counts.sum(), 1)

    # avoid log(0) / division by zero with a small epsilon floor
    eps = 1e-4
    train_pct = np.clip(train_pct, eps, None)
    new_pct = np.clip(new_pct, eps, None)

    psi = float(np.sum((new_pct - train_pct) * np.log(new_pct / train_pct)))
    return round(psi, 4)


def compute_drift_for_feature(train_values: pd.Series, new_values: pd.Series, feature_name: str) -> DriftResult:
    psi = compute_psi(train_values.values, new_values.values)
    ks_stat, ks_pvalue = stats.ks_2samp(train_values.dropna(), new_values.dropna())

    return DriftResult(
        feature=feature_name,
        psi=psi,
        psi_drift_detected=psi > settings.PSI_DRIFT_THRESHOLD,
        ks_statistic=round(float(ks_stat), 4),
        ks_pvalue=round(float(ks_pvalue), 6),
        ks_drift_detected=ks_pvalue < settings.KS_PVALUE_THRESHOLD,
    )


def compute_drift_report(train_df: pd.DataFrame, new_df: pd.DataFrame, features: list[str]) -> list[DriftResult]:
    results = []
    for feat in features:
        if feat not in train_df.columns or feat not in new_df.columns:
            continue
        results.append(compute_drift_for_feature(train_df[feat], new_df[feat], feat))
    return results


@dataclass
class RetrainingDecision:
    should_retrain: bool
    reasons: list[str]
    checked_at: str


def evaluate_retraining_policy(
    drift_results: list[DriftResult],
    current_mape: float | None = None,
    baseline_mape: float | None = None,
    days_since_last_training: int | None = None,
    manual_trigger: bool = False,
) -> RetrainingDecision:
    """
    Evaluates the explicit retraining policy from Part 6. Any one
    condition being true is sufficient to trigger retraining.
    """
    reasons = []

    drifted_features = [d.feature for d in drift_results if d.psi_drift_detected]
    if drifted_features:
        reasons.append(f"PSI drift > {settings.PSI_DRIFT_THRESHOLD} on features: {drifted_features}")

    if current_mape is not None and baseline_mape is not None and baseline_mape > 0:
        mape_increase_pct = (current_mape - baseline_mape) / baseline_mape * 100
        if mape_increase_pct > settings.MAPE_DEGRADATION_THRESHOLD_PCT:
            reasons.append(
                f"Forecast MAPE increased {mape_increase_pct:.1f}% from baseline "
                f"(threshold {settings.MAPE_DEGRADATION_THRESHOLD_PCT}%)"
            )

    if days_since_last_training is not None and days_since_last_training >= 7:
        reasons.append(f"Weekly schedule elapsed ({days_since_last_training} days since last training)")

    if manual_trigger:
        reasons.append("Manual trigger via API")

    return RetrainingDecision(
        should_retrain=len(reasons) > 0,
        reasons=reasons,
        checked_at=datetime.now(timezone.utc).isoformat(),
    )


if __name__ == "__main__":
    np.random.seed(42)
    # simulate genuine drift: training distribution N(50, 10), new distribution N(65, 12)
    train_cpu = pd.Series(np.random.normal(50, 10, 1000))
    new_cpu_drifted = pd.Series(np.random.normal(65, 12, 300))
    new_cpu_stable = pd.Series(np.random.normal(50, 10, 300))

    print("=== Drifted feature ===")
    result_drifted = compute_drift_for_feature(train_cpu, new_cpu_drifted, "cpu_avg_pct")
    print(result_drifted)

    print("\n=== Stable feature ===")
    result_stable = compute_drift_for_feature(train_cpu, new_cpu_stable, "cpu_avg_pct")
    print(result_stable)

    print("\n=== Retraining policy evaluation (drifted case) ===")
    decision = evaluate_retraining_policy(
        [result_drifted], current_mape=9.2, baseline_mape=6.5, days_since_last_training=3
    )
    print(decision)

    print("\n=== Retraining policy evaluation (stable case, no triggers) ===")
    decision_stable = evaluate_retraining_policy(
        [result_stable], current_mape=6.6, baseline_mape=6.5, days_since_last_training=2
    )
    print(decision_stable)

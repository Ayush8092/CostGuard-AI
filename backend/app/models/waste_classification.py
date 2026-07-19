"""
Model 3 - Waste Classification (Part 3).

waste_score is a multi-signal composite SCORING FUNCTION (not a model -
labeled correctly per Part 10), computed directly from raw features:

  waste_score = (
      0.30 * (100 - cpu_avg_pct) / 100 +
      0.20 * (100 - memory_avg_pct) / 100 +
      0.20 * normalized(cost_growth_rate) +
      0.20 * (idle_days / 30) +
      0.10 * (1 if anomaly_history_count > 0 else 0)
  ) * 100

Weights re-normalize if a signal is unavailable (graceful degradation,
same pattern as Tier 3 CSV upload). Buckets:
  0-25 Healthy | 25-50 Underutilized | 50-75 Idle | 75-100 Critical Waste

The CLASSIFIER (Random Forest) is trained on the raw underlying features
(cpu, memory, cost, runtime, cost_growth_rate, anomaly_history_count) -
it is NEVER trained directly on waste_score, so it has to learn the
interaction pattern itself rather than memorizing the formula. Its own
predicted bucket (predicted_bucket) is reported alongside the
formula-derived bucket (bucket) so the two can be compared.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split

BASE_WASTE_WEIGHTS = {
    "cpu_term": 0.30,
    "memory_term": 0.20,
    "cost_growth_term": 0.20,
    "idle_days_term": 0.20,
    "anomaly_history_term": 0.10,
}

BUCKET_BANDS = [(75, "Critical Waste"), (50, "Idle"), (25, "Underutilized"), (0, "Healthy")]

RAW_FEATURE_COLS = ["cpu_avg_pct", "memory_avg_pct", "cost", "runtime_days", "cost_growth_rate", "anomaly_history_count"]


def _bucket_for_score(score: float) -> str:
    for threshold, label in BUCKET_BANDS:
        if score >= threshold:
            return label
    return "Healthy"


def _normalize_cost_growth(series: pd.Series) -> pd.Series:
    """Min-max normalize cost_growth_rate into [0, 1] for use inside the waste_score formula."""
    lo, hi = series.min(), series.max()
    if hi - lo < 1e-9:
        return pd.Series(np.zeros(len(series)), index=series.index)
    return ((series - lo) / (hi - lo)).clip(0, 1)


def _compute_idle_days(df: pd.DataFrame, group_col: str = "resource_id", date_col: str = "date",
                        cpu_col: str = "cpu_avg_pct", idle_threshold_pct: float = 10.0, window_days: int = 30) -> pd.Series:
    """Rolling count, within the trailing window_days, of days where cpu_avg_pct was below idle_threshold_pct."""
    out = df.sort_values([group_col, date_col]).copy()
    is_idle = (out[cpu_col] < idle_threshold_pct).astype(int)
    idle_days = is_idle.groupby(out[group_col]).transform(lambda s: s.rolling(window_days, min_periods=1).sum())
    return idle_days.reindex(df.index)


def compute_waste_score(df: pd.DataFrame) -> tuple[pd.Series, dict[str, float]]:
    """
    Computes the waste_score scoring function row-by-row, re-normalizing
    weights for any signal whose source column is missing from df.
    Returns (waste_score_series, weights_actually_used).
    """
    out = df.copy()
    available_signals = {}

    if "cpu_avg_pct" in out.columns:
        available_signals["cpu_term"] = (100 - out["cpu_avg_pct"]) / 100
    if "memory_avg_pct" in out.columns:
        available_signals["memory_term"] = (100 - out["memory_avg_pct"]) / 100
    if "cost_growth_rate" in out.columns:
        available_signals["cost_growth_term"] = _normalize_cost_growth(out["cost_growth_rate"])
    if "cpu_avg_pct" in out.columns:
        idle_days = _compute_idle_days(out)
        available_signals["idle_days_term"] = (idle_days / 30).clip(0, 1)
    if "anomaly_history_count" in out.columns:
        available_signals["anomaly_history_term"] = (out["anomaly_history_count"] > 0).astype(float)

    weights = {k: BASE_WASTE_WEIGHTS[k] for k in available_signals}
    weight_sum = sum(weights.values())
    weights = {k: w / weight_sum for k, w in weights.items()} if weight_sum > 0 else weights

    score = pd.Series(np.zeros(len(out)), index=out.index)
    for term, series in available_signals.items():
        score += series.fillna(0.0) * weights[term]
    score = (score * 100).round(2)

    return score, weights


@dataclass
class WasteClassifierEvaluation:
    accuracy: float
    precision_macro: float
    recall_macro: float
    f1_macro: float
    confusion_matrix: list[list[int]]
    class_labels: list[str]


class WasteClassifier:
    """Random Forest classifier trained on RAW features, never on waste_score itself."""

    def __init__(self):
        self.model = RandomForestClassifier(n_estimators=200, max_depth=8, random_state=42, class_weight="balanced")
        self.feature_cols = RAW_FEATURE_COLS
        self.classes_: list[str] = []

    def fit(self, X: pd.DataFrame, y: pd.Series) -> None:
        X_filled = X[self.feature_cols].fillna(0)
        self.model.fit(X_filled, y)
        self.classes_ = list(self.model.classes_)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        X_filled = X[self.feature_cols].fillna(0)
        return self.model.predict(X_filled)

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        X_filled = X[self.feature_cols].fillna(0)
        return self.model.predict_proba(X_filled)

    def evaluate(self, X_test: pd.DataFrame, y_test: pd.Series) -> WasteClassifierEvaluation:
        y_pred = self.predict(X_test)
        labels = sorted(set(y_test) | set(y_pred))
        cm = confusion_matrix(y_test, y_pred, labels=labels)
        return WasteClassifierEvaluation(
            accuracy=round(accuracy_score(y_test, y_pred), 4),
            precision_macro=round(precision_score(y_test, y_pred, average="macro", zero_division=0), 4),
            recall_macro=round(recall_score(y_test, y_pred, average="macro", zero_division=0), 4),
            f1_macro=round(f1_score(y_test, y_pred, average="macro", zero_division=0), 4),
            confusion_matrix=cm.tolist(),
            class_labels=labels,
        )


def train_waste_classifier(df: pd.DataFrame, test_size: float = 0.2) -> tuple[WasteClassifier, WasteClassifierEvaluation, pd.DataFrame]:
    """
    Computes waste_score + bucket labels (the supervisory signal), then
    trains the classifier on RAW features with a stratified 80/20 split,
    per spec.
    """
    out = df.copy()
    waste_score, weights = compute_waste_score(out)
    out["waste_score"] = waste_score
    out["bucket"] = waste_score.apply(_bucket_for_score)

    X = out[RAW_FEATURE_COLS].fillna(0)
    y = out["bucket"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=42, stratify=y
    )

    classifier = WasteClassifier()
    classifier.fit(X_train, y_train)
    evaluation = classifier.evaluate(X_test, y_test)

    out.loc[X_test.index, "predicted_bucket"] = classifier.predict(X_test)

    return classifier, evaluation, out


if __name__ == "__main__":
    billing = pd.read_csv("app/data/synthetic/billing_data.csv", parse_dates=["date"])

    classifier, evaluation, scored_df = train_waste_classifier(billing)

    print("Bucket distribution (from waste_score formula):")
    print(scored_df["bucket"].value_counts())
    print()
    print("Classifier evaluation (trained on raw features, never on waste_score):")
    print(f"  Accuracy:       {evaluation.accuracy}")
    print(f"  Precision(macro): {evaluation.precision_macro}")
    print(f"  Recall(macro):    {evaluation.recall_macro}")
    print(f"  F1(macro):        {evaluation.f1_macro}")
    print(f"  Class labels:     {evaluation.class_labels}")
    print(f"  Confusion matrix:")
    for row in evaluation.confusion_matrix:
        print(f"    {row}")

    print()
    print("Sample scored rows:")
    print(scored_df[["resource_id", "date", "cpu_avg_pct", "memory_avg_pct", "waste_score", "bucket"]].head(5))

"""
Explainability (Part 3) - shap.TreeExplainer on the forecasting and
waste-classification models.

Surfaces the top contributing features per prediction, in the exact
shape the spec asks for: human-readable deltas like "resource count
+32%, storage usage +21%, traffic +18%" suitable both as a dashboard
chart and as grounding context fed into LLM explanations. The LLM layer
(Part 4) only ever restates these real SHAP numbers - it never invents
its own feature attributions.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import shap

from app.models.waste_classification import RAW_FEATURE_COLS, WasteClassifier
from app.models.forecasting import FEATURE_COLS, HierarchicalForecaster


@dataclass
class FeatureContribution:
    feature: str
    shap_value: float
    feature_value: float
    direction: str  # "increased" | "decreased"


@dataclass
class ExplanationResult:
    top_contributions: list[FeatureContribution]
    base_value: float
    prediction: float

    def to_narrative_fragments(self, top_n: int = 3) -> list[str]:
        """
        Produces short human-readable fragments like the spec's example:
        "resource count +32%, storage usage +21%, traffic +18%". These
        fragments are the ONLY numbers the LLM layer is allowed to use
        when explaining a forecast or recommendation - grounding, not
        invention.
        """
        fragments = []
        for c in self.top_contributions[:top_n]:
            sign = "+" if c.direction == "increased" else "-"
            pct_like = abs(c.shap_value)
            fragments.append(f"{c.feature.replace('_', ' ')} {sign}{pct_like:.2f}")
        return fragments


def explain_forecast_prediction(
    forecaster: HierarchicalForecaster,
    X_row: pd.DataFrame,
    top_n: int = 5,
) -> ExplanationResult:
    """Explains a single forecast row using the median (50th percentile) model."""
    model = forecaster.models[0.50]
    explainer = shap.TreeExplainer(model)
    X_filled = X_row[forecaster.feature_cols].fillna(0)
    shap_values = explainer.shap_values(X_filled)

    row_shap = shap_values[0] if shap_values.ndim == 2 else shap_values
    contributions = []
    for i, feat in enumerate(forecaster.feature_cols):
        val = float(row_shap[i])
        contributions.append(FeatureContribution(
            feature=feat,
            shap_value=round(val, 4),
            feature_value=float(X_filled.iloc[0][feat]),
            direction="increased" if val > 0 else "decreased",
        ))
    contributions.sort(key=lambda c: abs(c.shap_value), reverse=True)

    base_value = float(explainer.expected_value)
    prediction = base_value + float(np.sum(row_shap))

    return ExplanationResult(top_contributions=contributions[:top_n], base_value=base_value, prediction=prediction)


def explain_waste_prediction(
    classifier: WasteClassifier,
    X_row: pd.DataFrame,
    top_n: int = 5,
) -> dict[str, ExplanationResult]:
    """
    Explains a single waste-classification row. Random Forest is
    multi-class, so TreeExplainer returns one SHAP value set per class -
    we return an explanation per class so the dashboard can show "why
    this resource was NOT classified as Healthy" as well as why it was.
    """
    explainer = shap.TreeExplainer(classifier.model)
    X_filled = X_row[classifier.feature_cols].fillna(0)
    shap_values = explainer.shap_values(X_filled)

    results: dict[str, ExplanationResult] = {}
    # shap_values shape for multi-class TreeExplainer: (n_samples, n_features, n_classes)
    for class_idx, class_label in enumerate(classifier.classes_):
        if shap_values.ndim == 3:
            row_shap = shap_values[0, :, class_idx]
        else:
            row_shap = shap_values[class_idx][0]

        contributions = []
        for i, feat in enumerate(classifier.feature_cols):
            val = float(row_shap[i])
            contributions.append(FeatureContribution(
                feature=feat,
                shap_value=round(val, 4),
                feature_value=float(X_filled.iloc[0][feat]),
                direction="increased" if val > 0 else "decreased",
            ))
        contributions.sort(key=lambda c: abs(c.shap_value), reverse=True)

        base = explainer.expected_value
        base_value = float(base[class_idx]) if hasattr(base, "__len__") else float(base)
        results[class_label] = ExplanationResult(
            top_contributions=contributions[:top_n],
            base_value=base_value,
            prediction=base_value + float(np.sum(row_shap)),
        )

    return results


if __name__ == "__main__":
    from app.models.forecasting import train_and_evaluate_level
    from app.models.waste_classification import train_waste_classifier

    billing = pd.read_csv("app/data/synthetic/billing_data.csv", parse_dates=["date"])

    print("=" * 70)
    print("FORECAST EXPLANATION (one row)")
    print("=" * 70)
    forecaster, evaluation, train_df, test_df = train_and_evaluate_level(billing, level="org_total")
    sample_row = test_df.iloc[[0]]
    explanation = explain_forecast_prediction(forecaster, sample_row)
    print(f"Base value: {explanation.base_value:.2f}, Prediction: {explanation.prediction:.2f}")
    for c in explanation.top_contributions:
        print(f"  {c.feature:25s} shap={c.shap_value:+.4f}  value={c.feature_value:.2f}  ({c.direction})")
    print("Narrative fragments:", explanation.to_narrative_fragments())

    print()
    print("=" * 70)
    print("WASTE CLASSIFICATION EXPLANATION (one row)")
    print("=" * 70)
    classifier, waste_eval, scored_df = train_waste_classifier(billing)
    sample_waste_row = scored_df.iloc[[0]]
    waste_explanations = explain_waste_prediction(classifier, sample_waste_row)
    actual_bucket = sample_waste_row["bucket"].iloc[0]
    print(f"Actual bucket (from waste_score formula): {actual_bucket}")
    for label, expl in waste_explanations.items():
        print(f"\n  Explanation for class '{label}' (prediction={expl.prediction:.3f}):")
        for c in expl.top_contributions[:3]:
            print(f"    {c.feature:25s} shap={c.shap_value:+.4f}  value={c.feature_value:.2f}")

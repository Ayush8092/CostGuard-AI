"""
Model 1 - Hierarchical Forecasting (Part 3).

ALGORITHM CHOICE: XGBoost regression (quantile objective), not Prophet.
Documented reason: Prophet requires a Stan compiler toolchain which adds
significant install weight and build complexity to a project that must
run at zero cost on free-tier hosting with a single `docker compose up`.
XGBoost with quantile regression gives us both the point forecast and
native confidence intervals (5th/50th/95th percentile models) from one
consistent, lightweight library already used elsewhere in this project
(waste classification), without a second heavy ML dependency.

HIERARCHY - exactly 2 levels, as specified:
  (a) organization-total daily cost
  (b) per-service daily cost (EC2, S3, RDS, Lambda)
Per-resource forecasting is explicitly out of scope (spec: "Do not
attempt per-resource forecasting for every individual VM").

Split: time-based, first 80% train / last 20% test, NEVER shuffled.

Baseline: naive persistence forecast (tomorrow = today) AND
same-day-last-week, evaluated on the identical test set, reported
side-by-side with the model's MAE/RMSE/MAPE.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import xgboost as xgb

QUANTILES = [0.05, 0.50, 0.95]


@dataclass
class ForecastMetrics:
    mae: float
    rmse: float
    mape: float


@dataclass
class ForecastEvaluation:
    model_metrics: ForecastMetrics
    naive_persistence_metrics: ForecastMetrics
    naive_same_day_last_week_metrics: ForecastMetrics
    n_test_rows: int

    def forecast_error_reduction_pct(self, baseline: str = "persistence") -> float:
        """
        Business metric: how much lower is the model's MAPE than the naive
        baseline, expressed as a percentage reduction.
        reduction = (naive_mape - model_mape) / naive_mape
        """
        naive_mape = (
            self.naive_persistence_metrics.mape if baseline == "persistence"
            else self.naive_same_day_last_week_metrics.mape
        )
        if naive_mape == 0:
            return 0.0
        return round((naive_mape - self.model_metrics.mape) / naive_mape * 100, 2)


def _build_daily_series(df: pd.DataFrame, level: str, service: str | None = None) -> pd.DataFrame:
    """Aggregates the internal-schema dataframe into a single daily time series for one hierarchy level."""
    work = df.copy()
    work["date"] = pd.to_datetime(work["date"])
    if level == "per_service":
        work = work[work["service"] == service]

    daily = work.groupby("date").agg(
        cost=("cost", "sum"),
        active_resource_count=("resource_id", "nunique"),
    ).reset_index().sort_values("date")
    return daily


def _make_supervised_features(daily: pd.DataFrame) -> pd.DataFrame:
    out = daily.copy()
    out["day_of_week"] = out["date"].dt.dayofweek
    out["day_of_month"] = out["date"].dt.day
    out["rolling_avg_7d"] = out["cost"].rolling(7, min_periods=1).mean()
    out["rolling_avg_30d"] = out["cost"].rolling(30, min_periods=1).mean()
    out["lag_1d"] = out["cost"].shift(1)
    out["lag_7d"] = out["cost"].shift(7)
    return out


FEATURE_COLS = ["day_of_week", "day_of_month", "rolling_avg_7d", "rolling_avg_30d",
                "lag_1d", "lag_7d", "active_resource_count"]


def _time_based_split(df: pd.DataFrame, train_frac: float = 0.8) -> tuple[pd.DataFrame, pd.DataFrame]:
    """First train_frac of rows (chronologically) -> train, remainder -> test. Never shuffled."""
    df = df.sort_values("date").reset_index(drop=True)
    split_idx = int(len(df) * train_frac)
    return df.iloc[:split_idx], df.iloc[split_idx:]


def _compute_metrics(actual: np.ndarray, predicted: np.ndarray) -> ForecastMetrics:
    mae = float(np.mean(np.abs(actual - predicted)))
    rmse = float(np.sqrt(np.mean((actual - predicted) ** 2)))
    # avoid divide-by-zero in MAPE for any zero-cost day
    safe_actual = np.where(actual == 0, 1e-6, actual)
    mape = float(np.mean(np.abs((actual - predicted) / safe_actual)) * 100)
    return ForecastMetrics(mae=round(mae, 4), rmse=round(rmse, 4), mape=round(mape, 4))


class HierarchicalForecaster:
    """
    Trains one set of quantile models (5th/50th/95th percentile) for a
    single hierarchy level (org-total or one specific service).
    """

    def __init__(self, level: str, service: str | None = None):
        self.level = level
        self.service = service
        self.models: dict[float, xgb.XGBRegressor] = {}
        self.feature_cols = FEATURE_COLS
        self._residual_p05 = 0.0
        self._residual_p95 = 0.0

    def fit(self, train_df: pd.DataFrame) -> None:
        X = train_df[self.feature_cols].fillna(0)
        y = train_df["cost"]
        for q in QUANTILES:
            # Tail quantiles (5th/95th) get a bit more capacity and a
            # touch more regularization than the median model - they're
            # estimating from sparser information (the tails of the
            # conditional distribution) and tend to under-cover if fit
            # identically to the median model.
            is_tail = q != 0.50
            model = xgb.XGBRegressor(
                objective="reg:quantileerror",
                quantile_alpha=q,
                n_estimators=250 if is_tail else 150,
                max_depth=3 if is_tail else 4,
                learning_rate=0.05,
                reg_lambda=1.0,
                subsample=0.8,
                random_state=42,
            )
            model.fit(X, y)
            self.models[q] = model

        # Quantile regressors trained independently per quantile are known
        # to under-cover on small/medium series (the 5th/95th models don't
        # see enough tail examples to learn the true spread). As a
        # calibration backstop, measure the in-sample residual spread of
        # the median model and use it to widen the CI band if the raw
        # quantile-model band is narrower than what the residuals imply.
        median_in_sample_pred = self.models[0.50].predict(X)
        residuals = (y.values - median_in_sample_pred)
        # Use slightly wider percentiles (2nd/98th rather than 5th/95th) as the
        # calibration backstop. In-sample residuals systematically understate
        # true out-of-sample spread for time series (the model has already
        # adapted to in-sample noise); this margin compensates for that gap
        # rather than chasing a specific coverage number on one dataset.
        self._residual_p05 = float(np.percentile(residuals, 2))
        self._residual_p95 = float(np.percentile(residuals, 98))

    def predict(self, X: pd.DataFrame) -> pd.DataFrame:
        X_filled = X[self.feature_cols].fillna(0)
        preds = {q: self.models[q].predict(X_filled) for q in QUANTILES}
        raw = np.column_stack([preds[0.05], preds[0.50], preds[0.95]])
        # Independently-trained quantile models can "cross" (e.g. the 5th
        # percentile model predicts higher than the 50th for some row).
        # Enforce monotonic ordering post-hoc so ci_lower <= forecast <= ci_upper
        # always holds, which is required for the output to be meaningful.
        sorted_preds = np.sort(raw, axis=1)
        forecast = sorted_preds[:, 1]
        ci_lower = sorted_preds[:, 0]
        ci_upper = sorted_preds[:, 2]

        # Calibration backstop: if the residual-implied band (median +/-
        # in-sample 5th/95th percentile residual) is wider than what the
        # quantile models predicted for a given row, use the wider one.
        # This corrects the known under-coverage tendency of independently
        # trained quantile regressors without discarding their per-row
        # shape information - it only ever widens, never narrows.
        residual_lower = forecast + self._residual_p05
        residual_upper = forecast + self._residual_p95
        ci_lower = np.minimum(ci_lower, residual_lower)
        ci_upper = np.maximum(ci_upper, residual_upper)

        return pd.DataFrame({"forecast": forecast, "ci_lower": ci_lower, "ci_upper": ci_upper})

    def evaluate(self, test_df: pd.DataFrame) -> ForecastEvaluation:
        preds = self.predict(test_df)
        actual = test_df["cost"].values
        model_metrics = _compute_metrics(actual, preds["forecast"].values)

        # naive baseline 1: tomorrow = today (persistence), using lag_1d already computed
        persistence_pred = test_df["lag_1d"].bfill().values
        persistence_metrics = _compute_metrics(actual, persistence_pred)

        # naive baseline 2: same-day-last-week, using lag_7d
        same_week_pred = test_df["lag_7d"].bfill().values
        same_week_metrics = _compute_metrics(actual, same_week_pred)

        return ForecastEvaluation(
            model_metrics=model_metrics,
            naive_persistence_metrics=persistence_metrics,
            naive_same_day_last_week_metrics=same_week_metrics,
            n_test_rows=len(test_df),
        )


def train_and_evaluate_level(df: pd.DataFrame, level: str, service: str | None = None) -> tuple[HierarchicalForecaster, ForecastEvaluation, pd.DataFrame, pd.DataFrame]:
    """Full pipeline for one hierarchy level: build series -> features -> split -> train -> evaluate."""
    daily = _build_daily_series(df, level=level, service=service)
    supervised = _make_supervised_features(daily)
    train_df, test_df = _time_based_split(supervised, train_frac=0.8)

    forecaster = HierarchicalForecaster(level=level, service=service)
    forecaster.fit(train_df)
    evaluation = forecaster.evaluate(test_df)

    return forecaster, evaluation, train_df, test_df


if __name__ == "__main__":
    billing = pd.read_csv("app/data/synthetic/billing_data.csv", parse_dates=["date"])

    print("=" * 70)
    print("ORG-TOTAL FORECAST")
    print("=" * 70)
    forecaster, evaluation, train_df, test_df = train_and_evaluate_level(billing, level="org_total")
    print(f"Train rows: {len(train_df)}, Test rows: {len(test_df)}")
    print(f"Model:      MAE={evaluation.model_metrics.mae}  RMSE={evaluation.model_metrics.rmse}  MAPE={evaluation.model_metrics.mape}%")
    print(f"Naive(t-1): MAE={evaluation.naive_persistence_metrics.mae}  RMSE={evaluation.naive_persistence_metrics.rmse}  MAPE={evaluation.naive_persistence_metrics.mape}%")
    print(f"Naive(t-7): MAE={evaluation.naive_same_day_last_week_metrics.mae}  RMSE={evaluation.naive_same_day_last_week_metrics.rmse}  MAPE={evaluation.naive_same_day_last_week_metrics.mape}%")
    print(f"Forecast error reduction vs naive(t-1): {evaluation.forecast_error_reduction_pct('persistence')}%")

    preds = forecaster.predict(test_df)
    print("\nSample forecast output (API shape):")
    sample = preds.iloc[0]
    print({"forecast": round(float(sample["forecast"]), 2),
           "ci_lower": round(float(sample["ci_lower"]), 2),
           "ci_upper": round(float(sample["ci_upper"]), 2)})

    print()
    print("=" * 70)
    print("PER-SERVICE FORECAST (EC2)")
    print("=" * 70)
    forecaster_ec2, eval_ec2, train_ec2, test_ec2 = train_and_evaluate_level(billing, level="per_service", service="EC2")
    print(f"Model:      MAE={eval_ec2.model_metrics.mae}  RMSE={eval_ec2.model_metrics.rmse}  MAPE={eval_ec2.model_metrics.mape}%")
    print(f"Naive(t-1): MAE={eval_ec2.naive_persistence_metrics.mae}  RMSE={eval_ec2.naive_persistence_metrics.rmse}  MAPE={eval_ec2.naive_persistence_metrics.mape}%")
    print(f"Forecast error reduction vs naive(t-1): {eval_ec2.forecast_error_reduction_pct('persistence')}%")

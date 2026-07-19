"""
Tier 2 - Schema-agnostic pricing ingestion (Part 1).

Pricing files arrive as Excel/CSV with inconsistent schemas across
vendors. We classify each file by its COLUMN SIGNATURE, never by
filename, because filenames are unreliable in the real world (this is
exactly why demo_data.xlsx and demo_ap_south_2.xlsx have generic names
but very different schemas).

Detected columns                         -> Classified as
Instance Type, Price, Region             -> on_demand
Spot Price, Availability Zone, Timestamp -> spot
Predicted Price, Forecast, Confidence    -> prediction

Files matching no known signature are flagged for manual column mapping,
never silently dropped, per the spec.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

import pandas as pd

PricingType = str  # "on_demand" | "spot" | "prediction" | "unknown"


def _norm(col: str) -> str:
    """Lowercase, strip, collapse whitespace/underscores for robust matching."""
    return re.sub(r"[\s_]+", "", col.strip().lower())


# signature: set of normalized substrings we look for in the normalized column names
SIGNATURES: dict[PricingType, dict[str, list[str]]] = {
    "on_demand": {
        "required_any": [["instancetype", "instantype"], ["price"], ["region"]],
    },
    "spot": {
        "required_any": [["spotprice"], ["availabilityzone", "az"], ["timestamp", "date"]],
    },
    "prediction": {
        "required_any": [["priceprediction", "predictedprice", "forecast"], ["confidence", "spotprice"]],
    },
}


@dataclass
class ClassificationResult:
    file_path: str
    sheet_name: str | None
    classified_as: PricingType
    matched_columns: dict[str, str]  # canonical_name -> original_column_name
    raw_columns: list[str]
    needs_manual_mapping: bool


def _read_any(file_path: str) -> dict[str, pd.DataFrame]:
    """Returns {sheet_name: df}. CSV files get a single pseudo-sheet 'csv'."""
    if file_path.lower().endswith(".csv"):
        return {"csv": pd.read_csv(file_path)}
    xl = pd.ExcelFile(file_path)
    return {sheet: xl.parse(sheet) for sheet in xl.sheet_names}


def classify_columns(columns: list[str]) -> tuple[PricingType, dict[str, str]]:
    """
    Returns (classified_type, matched_columns) where matched_columns maps
    a canonical field name (e.g. 'price', 'region') to the original column
    name actually present in the file.
    """
    norm_map = {_norm(c): c for c in columns}
    norm_keys = set(norm_map.keys())

    def find(substrings: list[str]) -> str | None:
        for sub in substrings:
            for nk in norm_keys:
                if sub in nk:
                    return norm_map[nk]
        return None

    # Prediction is the most specific signature - a file with a predicted/forecast
    # price column is a prediction dataset even if it also carries a real spot
    # price column for comparison (as ours does: Real_AWS_SpotPrice + Price_Prediction).
    pred_col = find(["pricepredict", "predictedprice", "forecast"])
    if pred_col:
        return "prediction", {
            "instance_type": find(["instancetype", "instantype"]) or "",
            "price": pred_col,
            "region": find(["availabilityzone", "az", "region"]) or "",
            "os": find(["productdescription", "os"]) or "",
            "date": find(["timestamp", "date"]) or "",
            "actual_price": find(["realaws", "actualprice", "spotprice"]) or "",
            "confidence": find(["confidence"]) or "",
        }

    # On-demand: instance type + price + region (and not itself a spot-price column)
    instance_col = find(["instancetype", "instantype"])
    price_col = find(["price"])
    region_col = find(["region"])
    if instance_col and price_col and region_col and "spot" not in _norm(price_col):
        return "on_demand", {"instance_type": instance_col, "price": price_col, "region": region_col,
                              "os": find(["os", "productdescription"]) or "", "date": find(["date"]) or ""}

    # Spot: spot price + AZ + timestamp
    spot_price_col = find(["spotprice"])
    az_col = find(["availabilityzone", "az"])
    ts_col = find(["timestamp"])
    if spot_price_col and az_col and ts_col:
        return "spot", {"instance_type": find(["instancetype", "instantype"]) or "", "price": spot_price_col,
                         "region": az_col, "os": find(["productdescription", "os"]) or "", "date": ts_col}

    return "unknown", {}


def classify_pricing_file(file_path: str) -> list[ClassificationResult]:
    sheets = _read_any(file_path)
    results = []
    for sheet_name, df in sheets.items():
        ptype, matched = classify_columns(list(df.columns))
        results.append(
            ClassificationResult(
                file_path=file_path,
                sheet_name=sheet_name if sheet_name != "csv" else None,
                classified_as=ptype,
                matched_columns=matched,
                raw_columns=list(df.columns),
                needs_manual_mapping=(ptype == "unknown"),
            )
        )
    return results


def classify_pricing_directory(directory: str) -> list[ClassificationResult]:
    all_results = []
    for fname in sorted(os.listdir(directory)):
        if fname.lower().endswith((".xlsx", ".xls", ".csv")):
            path = os.path.join(directory, fname)
            all_results.extend(classify_pricing_file(path))
    return all_results


if __name__ == "__main__":
    results = classify_pricing_directory("app/data/bronze/pricing_v1")
    for r in results:
        print(f"\nFile: {r.file_path}")
        print(f"  Classified as: {r.classified_as}")
        print(f"  Raw columns: {r.raw_columns}")
        print(f"  Matched: {r.matched_columns}")
        print(f"  Needs manual mapping: {r.needs_manual_mapping}")

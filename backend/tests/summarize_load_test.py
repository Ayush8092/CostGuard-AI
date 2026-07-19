"""
summarize_load_test.py - converts Locust CSV output to the JSON shape
the Model Monitoring tab reads from /app/data/load_test_results.json.

Usage (run after locust finishes):
    python summarize_load_test.py --stats load_test_results_stats.csv \
                                  --out /app/data/load_test_results.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone


def summarize(stats_csv_path: str, out_path: str) -> dict:
    try:
        import csv

        rows = []
        with open(stats_csv_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
    except FileNotFoundError:
        print(f"ERROR: {stats_csv_path} not found. Run locust first.", file=sys.stderr)
        sys.exit(1)

    # Locust stats CSV has an "Aggregated" row as the last entry
    aggregated = next((r for r in rows if r.get("Name") == "Aggregated"), None)
    if aggregated is None and rows:
        aggregated = rows[-1]

    if aggregated is None:
        print("ERROR: No rows found in stats CSV.", file=sys.stderr)
        sys.exit(1)

    # Per-endpoint rows for the latency breakdown table
    endpoint_rows = [r for r in rows if r.get("Name") not in ("Aggregated", "")]
    per_endpoint = {}
    for r in endpoint_rows:
        name = r.get("Name", "unknown")
        per_endpoint[name] = {
            "avg_latency_ms": round(float(r.get("Average Response Time", 0)), 1),
            "p95_latency_ms": round(float(r.get("95%", 0)), 1),
            "p99_latency_ms": round(float(r.get("99%", 0)), 1),
            "requests_per_sec": round(float(r.get("Requests/s", 0)), 2),
            "failure_count": int(r.get("Failure Count", 0)),
            "request_count": int(r.get("Request Count", 0)),
        }

    total_requests = int(aggregated.get("Request Count", 0))
    total_failures = int(aggregated.get("Failure Count", 0))
    error_rate_pct = round(total_failures / max(total_requests, 1) * 100, 2)

    result = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "simulated_users": 200,
        "run_time_seconds": 60,
        "avg_latency_ms": round(float(aggregated.get("Average Response Time", 0)), 1),
        "p95_latency_ms": round(float(aggregated.get("95%", 0)), 1),
        "p99_latency_ms": round(float(aggregated.get("99%", 0)), 1),
        "requests_per_sec": round(float(aggregated.get("Requests/s", 0)), 2),
        "total_requests": total_requests,
        "total_failures": total_failures,
        "error_rate_pct": error_rate_pct,
        "per_endpoint": per_endpoint,
        "pass": error_rate_pct < 1.0,
    }

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"Load test summary written to {out_path}")
    for k, v in result.items():
        if k != "per_endpoint":
            print(f"  {k}: {v}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stats", required=True, help="Locust _stats.csv file")
    parser.add_argument("--out", default="/app/data/load_test_results.json")
    args = parser.parse_args()
    summarize(args.stats, args.out)

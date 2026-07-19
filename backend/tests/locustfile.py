"""
Load testing (Part 8) - required deliverable, not optional.

Simulates 200 concurrent users across the four flows the spec names:
  1. Dashboard (GET /api/v1/dashboard)
  2. AI Copilot (POST /api/v1/copilot)
  3. Forecasting (GET /api/v1/forecast)
  4. Recommendations (GET /api/v1/recommendations)

Run against a live stack with:
    locust -f locustfile.py --host http://localhost --users 200 \
           --spawn-rate 10 --run-time 60s --headless \
           --csv load_test_results

The --csv flag writes per-request stats to CSV files; the summarize.py
helper (below) converts those into the JSON shape the Model Monitoring
tab expects at /app/data/load_test_results.json.

Interpretation of results:
  - Average latency < 200ms on dashboard/forecast/recommendation
    endpoints confirms "fast cached reads" behaviour.
  - Copilot latency will be higher (LLM call overhead) and is expected.
  - Error rate < 1% at 200 users is the pass criteria.
"""
from __future__ import annotations

import random

from locust import HttpUser, TaskSet, between, task


AUTH_EMAIL = "loadtest@costguard.local"
AUTH_PASSWORD = "LoadTest1234"

COPILOT_QUESTIONS = [
    "Why did my bill increase?",
    "Which instances should I terminate?",
    "Show idle resources",
    "Compare last month vs this month",
    "Which VM had the highest network usage?",
    "Forecast EC2 cost for next week",
]


class DashboardTasks(TaskSet):
    """Simulates a Viewer role browsing the read-only dashboard tabs."""

    @task(5)
    def dashboard_kpis(self):
        self.client.get("/api/v1/dashboard", name="/dashboard")

    @task(4)
    def forecast_org_total(self):
        self.client.get("/api/v1/forecast?level=org_total", name="/forecast [org_total]")

    @task(3)
    def forecast_per_service(self):
        service = random.choice(["EC2", "S3", "RDS", "Lambda"])
        self.client.get(
            f"/api/v1/forecast?level=per_service&service={service}",
            name="/forecast [per_service]",
        )

    @task(3)
    def recommendations(self):
        self.client.get("/api/v1/recommendations", name="/recommendations")

    @task(2)
    def anomalies(self):
        self.client.get("/api/v1/anomalies?limit=50", name="/anomalies")

    @task(2)
    def waste(self):
        self.client.get("/api/v1/waste", name="/waste")

    @task(1)
    def business_metrics(self):
        self.client.get("/api/v1/business-metrics", name="/business-metrics")

    @task(1)
    def model_registry(self):
        self.client.get("/api/v1/models/registry", name="/models/registry")

    @task(1)
    def weekly_report_latest(self):
        self.client.get("/api/v1/reports/weekly/latest", name="/reports/weekly/latest")


class CopilotTasks(TaskSet):
    """Simulates an Analyst using the AI Copilot — heavier weight on LLM endpoints."""

    @task(3)
    def ask_copilot(self):
        question = random.choice(COPILOT_QUESTIONS)
        self.client.post(
            "/api/v1/copilot",
            json={"question": question},
            name="/copilot",
        )

    @task(2)
    def dashboard_kpis(self):
        self.client.get("/api/v1/dashboard", name="/dashboard")

    @task(2)
    def recommendations(self):
        self.client.get("/api/v1/recommendations", name="/recommendations")

    @task(1)
    def simulator(self):
        # Use an intentionally bogus resource ID to exercise the
        # "resource not found" fast path without needing real data.
        self.client.post(
            "/api/v1/simulate",
            json={
                "actions": [{"resource_id": "loadtest-vm-000", "action_type": "terminate"}],
                "window_days": 30,
            },
            name="/simulate",
        )


class DashboardUser(HttpUser):
    """
    Represents a Viewer or light Analyst - mostly read-only dashboard
    browsing. 70% of the simulated user pool.
    """

    tasks = [DashboardTasks]
    wait_time = between(1, 4)

    def on_start(self):
        """Log in once per simulated user before running any tasks."""
        form_data = {"username": AUTH_EMAIL, "password": AUTH_PASSWORD}
        resp = self.client.post(
            "/api/v1/auth/login",
            data=form_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            name="/auth/login [setup]",
        )
        if resp.status_code == 200:
            token = resp.json().get("access_token", "")
            self.client.headers.update({"Authorization": f"Bearer {token}"})
        # If login fails (e.g. user not seeded yet), subsequent requests
        # will receive 401 and be counted as errors - this is correct
        # behaviour, not a test bug.


class CopilotUser(HttpUser):
    """
    Represents an Analyst who actively uses the Copilot. 30% of the
    simulated user pool. Higher inter-request wait to reflect realistic
    LLM interaction pacing (people read responses before asking again).
    """

    tasks = [CopilotTasks]
    wait_time = between(5, 15)

    def on_start(self):
        form_data = {"username": AUTH_EMAIL, "password": AUTH_PASSWORD}
        resp = self.client.post(
            "/api/v1/auth/login",
            data=form_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            name="/auth/login [setup]",
        )
        if resp.status_code == 200:
            token = resp.json().get("access_token", "")
            self.client.headers.update({"Authorization": f"Bearer {token}"})

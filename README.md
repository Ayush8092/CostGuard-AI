# CostGuard AI — FinOps Platform

AI-powered cloud cost optimization platform combining real ML (hierarchical
forecasting, multi-dimensional anomaly detection, waste classification) with a
grounded LLM "FinOps Copilot" layer. Runs at **$0** via self-hosted Docker and
free-tier LLM APIs.

---

## Quick Start

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env — only GROQ_API_KEY is strictly needed for full AI features.
# The app runs fully without it (stub mode).

# 2. Start everything
docker compose up --build

# 3. Open the app
# Dashboard:  http://localhost
# API docs:   http://localhost/api/v1/docs
```

That's it. One command. No paid dependencies.

---

## Data Honesty — Read This First

> **VM telemetry is real (Bitbrains GWA-T-12 trace). Cost is a computed
> estimate from a documented instance-matching and pricing-engine methodology —
> not an observed billing invoice.**

Anomaly detection precision/recall figures (F1 ≈ 0.28–0.40) are measured only
against the **synthetic dataset's known ground truth**. On real organization
data (Bitbrains CSV uploads, future live AWS), the model runs fully unsupervised
and flags candidates for human review. No accuracy figure is claimed or reported
for real data anywhere in this project.

---

## Stack

| Layer | Technology | Cost |
|---|---|---|
| Backend | FastAPI + Python 3.12 | Free |
| Frontend | React 18 + Vite + Tailwind CSS | Free |
| Database | PostgreSQL 16 | Free (self-hosted) |
| Cache / Queue | Redis 7 | Free (self-hosted) |
| Vector search | FAISS (CPU) | Free |
| ML models | XGBoost, scikit-learn, SHAP | Free |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2, CPU) | Free |
| LLM | Groq free tier (Llama 3.1 70B) or Gemini free tier | Free |
| Orchestration | Docker Compose | Free |
| Reverse proxy | Nginx | Free |

---

## Project Structure

```
costguard/
├── backend/
│   ├── app/
│   │   ├── api/routes/      # FastAPI route modules (12 files, 25 endpoints)
│   │   ├── core/            # Config, JWT auth, Redis cache, rate limiting
│   │   ├── data/            # Data tiers 1-3: synthetic, Bitbrains, CSV upload
│   │   ├── db/              # SQLAlchemy models (15 tables) + session
│   │   ├── features/        # Feature engineering + PostgreSQL feature store
│   │   ├── llm/             # Copilot, Advisor, Simulator, Weekly Report
│   │   ├── mlops/           # Drift detection, model registry
│   │   ├── models/          # Forecasting, anomaly detection, waste, SHAP, scoring
│   │   ├── rag/             # FAISS knowledge base + instance lookup
│   │   └── workers/         # Nightly batch job, APScheduler, CSV processor
│   ├── migrations/          # Alembic migration (0001_initial.py)
│   ├── tests/               # Locust load test + summarizer
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── api/             # Axios client with JWT interceptor
│   │   ├── components/      # AppShell, KpiCard, ConfidenceBadge, Status
│   │   ├── context/         # AuthContext (JWT state management)
│   │   └── pages/           # 10 tab pages (Dashboard → Settings)
│   ├── nginx.conf
│   └── Dockerfile
├── deploy/nginx/nginx.conf  # Top-level reverse proxy
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## ML Models — Formulas and Methodology

### Model 1 — Hierarchical Forecasting

**Algorithm:** XGBoost quantile regression (not Prophet).

**Reason for XGBoost over Prophet:** Prophet requires a Stan compiler toolchain,
adding significant install weight incompatible with a "zero cost, single
`docker compose up`" requirement. XGBoost with quantile regression delivers
the same confidence intervals from one consistent, already-required library.

**Hierarchy:**
- Level A: organization-total daily cost
- Level B: per-service daily cost (EC2, S3, RDS, Lambda)
- Per-resource forecasting is **explicitly out of scope** (spec §3).

**Train/test split:** First 80% chronologically → train. Last 20% → test.
Never shuffled.

**Confidence intervals:** Three independently-trained quantile models
(5th / 50th / 95th percentile). Monotonic ordering enforced post-hoc
(sort the three predictions per row) since independently-trained quantile
models can cross. CI bands are further widened using a residual-based
calibration backstop to correct the known under-coverage tendency of
independently-trained quantile regressors.

**Output format:** `{"forecast": 120, "ci_lower": 112, "ci_upper": 129}`
— never a single point estimate alone.

**Naive baselines (side-by-side comparison):**
- Persistence: tomorrow = today (lag-1)
- Same-day-last-week: lag-7

**Metrics reported:** MAE, RMSE, MAPE for both model and both baselines.

---

### Model 2 — Multi-Dimensional Anomaly Detection

**Algorithm:** One Isolation Forest per dimension (cost, CPU, memory,
network, disk), each trained on `[raw_value, resource_relative_z_score]`.

**Resource-relative z-score:** Each day's value is compared against a
30-day rolling mean/std computed from data ending 7 days prior (lagged
baseline). This lag is essential — a baseline that includes the ongoing
drift adapts to the drift, making slow leaks invisible. The lag prevents
this contamination.

**Fused incident score (scoring function, not a model):**
```
incident_score = (
    0.35 * anomaly_score_cost +
    0.20 * anomaly_score_cpu +
    0.15 * anomaly_score_memory +
    0.15 * anomaly_score_network +
    0.15 * anomaly_score_disk
) / sum_of_available_weights
```
Weights re-normalize if a dimension is unavailable.

**Threshold:** 97th percentile of the observed `incident_score`
distribution (chosen by sweeping percentiles 80–99 against synthetic
ground truth; F1 peaks at 97th–99th for a 5% contamination model).
This is a **configurable operating point**, not a fixed truth — expose
it in the UI to let operators tune the precision/recall tradeoff.

**Evaluation:** Precision/Recall/F1 measured **only against synthetic
ground truth** (where anomaly dates are known). On real data, the model
runs unsupervised and returns candidates for human review.

---

### Model 3 — Waste Classification

**Waste score (scoring FUNCTION, not a trained model):**
```
waste_score = (
    0.30 * (100 - cpu_avg_pct) / 100 +
    0.20 * (100 - memory_avg_pct) / 100 +
    0.20 * normalized(cost_growth_rate) +
    0.20 * (idle_days / 30) +
    0.10 * (1 if anomaly_history_count > 0 else 0)
) * 100
```
Weights re-normalize if any signal column is absent (graceful
degradation for raw AWS CUR exports without utilization data).

**Buckets:** 0–25 Healthy | 25–50 Underutilized | 50–75 Idle |
75–100 Critical Waste.

**Classifier:** Random Forest trained on **raw underlying features**
(cpu_avg_pct, memory_avg_pct, cost, runtime_days, cost_growth_rate,
anomaly_history_count) — never trained directly on `waste_score`, so
it must learn the interaction pattern rather than memorising the
formula. Its predicted bucket is reported alongside the formula-derived
bucket so both can be compared.

**Split:** Stratified 80/20. **Metrics:** Accuracy, Precision, Recall,
macro-F1, confusion matrix.

---

## Scoring Functions (not models)

Per spec Part 10 — these are formulas, not trained models. Labelled
correctly throughout the codebase:

**FinOps Risk Score (0–100):**
```
risk_score = (0.4 * norm(forecast_growth)
            + 0.3 * norm(waste_ratio)
            + 0.3 * norm(anomaly_count)) * 100
```

**Recommendation savings:**
```
savings = (current_hourly_rate - recommended_hourly_rate)
          × projected_runtime_hours
```

**Composite recommendation confidence:**
```
confidence = 0.35 * classifier_confidence   # predict_proba
           + 0.20 * anomaly_score           # normalized 0-1
           + 0.20 * forecast_uncertainty    # 1 - normalized CI width
           + 0.25 * data_quality_score      # from Part 1 validation
```
Not the LLM. Derived from ML model outputs only.

**Recommendation ranking (impact score):**
```
impact_score = estimated_monthly_savings × confidence_weight
```

---

## Business Metrics

| Metric | Formula |
|---|---|
| Estimated Monthly Savings | `current_monthly_cost - projected_monthly_cost` |
| Waste Detection Coverage | `recommendations / total_waste_resources × 100` |
| Forecast Error Reduction | `(naive_mape - model_mape) / naive_mape × 100` |
| Optimization Opportunity Rate | `resources_needing_opt / total_resources × 100` |
| Avg Recommendation Confidence | Mean composite confidence across all open recs |
| Idle Resource Reduction Potential | `recommended_for_termination / idle_resources × 100` |
| Infrastructure Health Score | `100 - risk_score` |
| Cost Efficiency Score | `useful_cpu_hours / total_cloud_cost` |

---

## Setup — PostgreSQL

### Using Docker Compose (recommended, zero setup)
The `postgres` service in `docker-compose.yml` handles everything.
Your data persists in the `postgres_data` Docker volume.

### Manual setup (if running Postgres outside Docker)
```sql
CREATE DATABASE costguard;
CREATE USER costguard WITH PASSWORD 'costguard_password';
GRANT ALL PRIVILEGES ON DATABASE costguard TO costguard;
```
Then update `.env`:
```
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=costguard
POSTGRES_USER=costguard
POSTGRES_PASSWORD=costguard_password
```
Run migrations:
```bash
cd backend
alembic upgrade head
```

### Free-tier hosted Postgres (if you don't want to run Docker locally)
- **Neon** — https://neon.tech (free tier, persistent, no expiry as of writing)
- **Supabase** — https://supabase.com (free tier, includes GUI)

Get the connection string from either service and set it in `.env` as:
```
POSTGRES_HOST=<host from provider>
POSTGRES_PORT=5432
POSTGRES_DB=<db name>
POSTGRES_USER=<user>
POSTGRES_PASSWORD=<password>
```

---

## Setup — Redis

### Using Docker Compose (recommended, zero setup)
The `redis` service in `docker-compose.yml` handles everything.

### Manual setup
```bash
# Ubuntu/Debian
sudo apt-get install redis-server
sudo systemctl start redis-server

# macOS
brew install redis
brew services start redis
```
Update `.env`:
```
REDIS_HOST=localhost
REDIS_PORT=6379
```

### Free-tier hosted Redis
- **Upstash** — https://upstash.com (free tier, persistent)

Get the Redis URL from Upstash and set in `.env`:
```
REDIS_HOST=<host>.upstash.io
REDIS_PORT=6379
```
Upstash requires TLS — also set `REDIS_URL=rediss://...` directly if
needed (the `rediss://` scheme enables TLS in redis-py).

---

## Setup — LLM API Key

### Option 1 — Groq (recommended, fastest free tier)
1. Sign up at https://console.groq.com
2. Create an API key at https://console.groq.com/keys
3. Add to `.env`: `GROQ_API_KEY=gsk_...`
4. Free tier limits change — check https://console.groq.com/docs/rate-limits

### Option 2 — Gemini
1. Get a free key at https://aistudio.google.com/app/apikey
2. Add to `.env`: `GEMINI_API_KEY=AI...` and `LLM_PROVIDER=gemini`

### Option 3 — Stub mode (no key needed)
Set `LLM_PROVIDER=none` in `.env`. The Copilot, Advisor, and Weekly
Report still work — they return clearly-labeled stub responses showing
what real answers would contain. All ML features (forecasting, anomaly
detection, waste classification, SHAP, scoring) are fully functional
regardless of LLM_PROVIDER.

---

## Setup — Bitbrains Full Dataset

The demo ships with small sample files in `backend/app/data/bronze/`.
To use the full Bitbrains GWA-T-12 dataset:

1. Place telemetry files (CSV/XLSX with the same schema as
   `Bitbrains_demo_1.xlsx`) in `backend/app/data/bronze/bitbrains_v1/`
2. Place pricing files in `backend/app/data/bronze/pricing_v1/`
3. Run the full pipeline:
   ```bash
   docker exec costguard-backend-1 python -m app.data.telemetry_silver
   docker exec costguard-backend-1 python -m app.data.pricing_silver
   docker exec costguard-backend-1 python -m app.data.telemetry_cost_engine
   ```
4. Trigger a nightly job run to retrain models on the new data:
   ```bash
   curl -X POST http://localhost/api/v1/models/retrain \
        -H "Authorization: Bearer <admin_token>"
   ```

---

## Load Testing

```bash
# Seed a load-test user first (requires a running stack)
curl -X POST http://localhost/api/v1/auth/signup \
     -H "Content-Type: application/json" \
     -d '{"organization_name":"LoadTestOrg","email":"loadtest@costguard.local","password":"LoadTest1234"}'

# Run the load test (200 users, 60 seconds)
cd backend
locust -f tests/locustfile.py --host http://localhost \
       --users 200 --spawn-rate 10 --run-time 60s --headless \
       --csv load_test_results

# Summarize results into the Model Monitoring tab format
python tests/summarize_load_test.py \
       --stats load_test_results_stats.csv \
       --out /app/data/load_test_results.json
```

The Model Monitoring tab will then show the real p95/p99/error-rate
numbers from the actual load test run.

**Pass criteria (Part 8):**
- Error rate < 1% at 200 concurrent users
- Average dashboard/forecast/recommendation latency < 200ms
  (these read from Redis cache — fast by design)
- Copilot latency is higher due to LLM call overhead; this is expected

---

## Multi-Tenancy

Every DB table that holds customer data is scoped by `organization_id`.
Every API route extracts `organization_id` from the JWT and passes it
to every DB query — no cross-tenant data leakage is possible without a
deliberately malformed token.

**RBAC roles:**
| Role | Can do |
|---|---|
| Admin | Everything, including triggering manual retrains and user management |
| Analyst | Read + write (upload CSVs, accept/dismiss recommendations) |
| Viewer | Read only |

---

## Nightly Job

Runs at `NIGHTLY_JOB_HOUR` UTC (default: 2am) via APScheduler embedded
in the FastAPI process. Covers:
1. Forecast models retrained per org + results written to `forecast_results`
2. Anomaly detection run + results written to `anomalies`
3. Waste classification run + results written to `waste_classifications`
4. Recommendations generated + written to `recommendations`
5. Model versions logged to `model_registry`

**Retraining triggers (Part 6):**
- PSI > 0.2 on any key feature
- Forecast MAPE increases > 15% from registered baseline
- Weekly schedule (7 days elapsed since last training)
- Manual trigger via `POST /api/v1/models/retrain` (admin only)

---

## v2 — Live AWS Cost Explorer (not built, not required for demo)

v2 adds a Tier 4 data source connecting directly to AWS Cost Explorer
via a **read-only cross-account IAM role + external ID**. Raw AWS
access keys are **never collected or stored** — this is explicitly
prohibited in the codebase and schema.

The AWS Cost Explorer API has historically carried a small per-request
fee even when the console itself is free. Verify current AWS pricing at
https://aws.amazon.com/aws-cost-management/pricing/ before enabling
this for any live account.

---

## What Is Not Built (Part 10 Explicit Exclusions)

- AI Incident Analyzer — excluded (duplicates another portfolio project)
- Standalone AI Knowledge Center tab — excluded (FAISS stays embedded in Copilot/Advisor only)
- Raw AWS Access Key/Secret Key storage — prohibited, IAM role only
- Fabricated metrics or placeholder numbers — none exist in this project
- "Multi-agent" labelling — the pipeline is correctly labelled "modular pipeline"
- Real-data anomaly/classification accuracy claims — never made

---

## License

MIT — free to use, modify, and deploy.

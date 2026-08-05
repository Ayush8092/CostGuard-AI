<div align="center">

# CostGuard AI

**AI-powered Cloud Cost Optimization Platform**

*Real ML forecasting · Multi-dimensional anomaly detection · LLM-grounded recommendations · $0 infrastructure*

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=black)](https://react.dev)
[![XGBoost](https://img.shields.io/badge/XGBoost-ML-FF6600?style=flat-square)](https://xgboost.readthedocs.io)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Neon-336791?style=flat-square&logo=postgresql&logoColor=white)](https://neon.tech)
[![Redis](https://img.shields.io/badge/Redis-Upstash-DC382D?style=flat-square&logo=redis&logoColor=white)](https://upstash.com)
[![License](https://img.shields.io/badge/License-MIT-16A34A?style=flat-square)](LICENSE)

</div>

---

## Overview

CostGuard AI is a production-grade, multi-tenant FinOps platform that combines real machine learning models with a grounded LLM layer to identify, quantify, and act on cloud cost inefficiencies.

Every metric displayed in the platform is derived from actual ML model outputs — no fabricated numbers, no placeholder data. The LLM layer narrates only what the models have computed.

```
Identified $2,220/month in savings · 65% forecast error reduction · 96.75% waste classifier accuracy
```

---

## System Architecture

![CostGuard AI – System Architecture](architecture_diagram.svg)

---

## Technology Stack

![CostGuard AI – Technology Stack](infographic_diagram.svg)

---

## End-to-End User Workflow

![CostGuard AI – User Workflow](User_Workflow.png)

---

## Key Metrics

| Metric | Value | Method |
|--------|-------|--------|
| Forecast error reduction | **65%** | XGBoost vs naive persistence baseline |
| Waste classifier accuracy | **96.75%** | Random Forest, stratified 80/20 split |
| Waste classifier macro-F1 | **0.958** | Across all 4 waste buckets |
| Avg recommendation confidence | **~92%** | Composite: classifier prob + anomaly score + forecast uncertainty |
| Waste detection coverage | **~95%** | Resources with actionable recommendation |
| Estimated monthly savings | **$2,220** | From real formula: current − projected spend |
| Anomaly detection F1 | **0.28–0.40** | Unsupervised on synthetic ground truth |
| Load test | **200 concurrent users** | Locust · dashboard endpoints sub-200ms |

> **Honesty note:** Precision/recall figures are measured against the synthetic dataset where ground truth is known. On real uploaded data the models run unsupervised and surface candidates for human review. No accuracy claims are made for real-world data.

---

## Machine Learning Pipeline

### Train-Once Serve-Many Architecture

The platform follows a strict separation between training and inference:

```
Nightly Schedule (02:00 UTC)
        │
        ▼
    Load Data from processed_telemetry
        │
        ▼
   Check Active Models
   ┌────┴────┐
   │         │
  Exist    Missing
   │         │
   │    Run full training
   │         │
   └────┬────┘
        ▼
   Load Active .pkl Artifacts
        │
        ▼
   Run Inference (no retraining)
        │
   ┌────┼────┬────────────┐
   ▼    ▼    ▼            ▼
Forecast Anomaly Waste  Recommendations
   │    │    │  + SHAP      │
   └────┴────┴────────────┘
        │
        ▼
   Store to PostgreSQL
        │
        ▼
   Invalidate Redis Cache
        │
        ▼
   Dashboard reads fresh data
```

**Retraining triggers** (weekly schedule + any of):
- PSI > 0.2 on any key feature (distribution shift)
- Forecast MAPE degrades > 15% from registered baseline
- Admin manual trigger via `POST /api/v1/models/retrain`
- New dataset upload in **Continuous Monitoring** mode

### Model 1 — Hierarchical Forecasting

| Property | Detail |
|----------|--------|
| Algorithm | XGBoost quantile regression |
| Hierarchy | Org-total + per-service (EC2, S3, RDS, Lambda) |
| Output | `{ forecast, ci_lower, ci_upper }` — never a point estimate alone |
| Confidence intervals | 5th / 50th / 95th percentile, monotonic ordering enforced |
| Baseline comparison | Persistence (lag-1) and same-day-last-week (lag-7) |
| Error reduction | **65%** MAPE reduction vs naive baseline |

### Model 2 — Multi-Dimensional Anomaly Detection

| Property | Detail |
|----------|--------|
| Algorithm | Isolation Forest, one model per signal dimension |
| Dimensions | cost, CPU, memory, network I/O, disk I/O |
| Key innovation | Resource-relative lagged z-score baseline prevents slow leaks from being masked by an adapting rolling window |
| Fusion | Weighted incident score across available dimensions |
| Threshold | 97th percentile of score distribution (configurable operating point) |
| Evaluation | Honest F1 0.28–0.40 on synthetic ground truth only |

### Model 3 — Waste Classification

| Property | Detail |
|----------|--------|
| Algorithm | Random Forest wrapped in sklearn `Pipeline` |
| Buckets | Healthy · Underutilized · Idle · Critical Waste |
| Training features | Raw telemetry (cpu_avg_pct, memory_avg_pct, cost, etc.) — never trained on the waste_score formula itself |
| Accuracy | **96.75%** · Macro-F1 **0.958** |
| Explainability | SHAP values computed at inference time, stored in DB, served on-demand |
| Inference | `pipeline.predict(df)` — preprocessing baked into artifact |

---

## Feature Highlights

### Dataset Versioning and Analysis History

Every upload creates a versioned dataset with a unique `dataset_id`. The entire dashboard, ML pipeline, and AI outputs are scoped to the active dataset. Switching datasets is instant — the sidebar works like ChatGPT conversation history.

```
Settings → Upload CSV → Choose Mode
                            │
             ┌──────────────┴──────────────┐
             ▼                             ▼
      New Analysis                Continuous Monitoring
      (isolated dataset)          (append to timeline)
      clears telemetry            continues forecast history
      becomes active view         preserves dashboard continuity
```

### Executive Insights

AI-written summary generated **once** after each analysis — not on every dashboard load. Stored per dataset, recalled instantly from the database.

```
Upload → ML Pipeline → LLM generates insight → Store → Display forever
                                                         (never re-call LLM)
```

### LLM Copilot

Intent detection → structured data query → FAISS retrieval → grounded LLM answer with citations.

Every answer cites the exact data source used. The LLM never invents figures — it narrates only what the ML models computed.

Supported question types:
- Why did my bill increase?
- Which instances should I terminate?
- Compare last month vs this month
- Which VM had the highest network usage?
- Forecast EC2 cost for next week
- Show idle resources

### Automatic LLM Fallback

```
LLM_PROVIDER=auto
      │
      ▼
Try Gemini (primary)
      │
   Rate limit?
   ┌──┴───┐
   Yes    No
   │      │
   ▼      ▼
 Groq   Return response
(silent fallback)
```
The end user never sees a switch. Non-quota errors surface normally.

---

## Data Tiers

| Tier | Source | Description |
|------|--------|-------------|
| 1 | Synthetic | 11,230 rows · 32 resources · 365 days · 24 labeled anomalies (idle, spike, slow leak) |
| 2 | Bitbrains GWA-T-12 | Real VM telemetry · cost estimated via deterministic instance-matching engine · confidence-gated |
| 3 | CSV Upload | Schema-agnostic · column alias mapping · graceful degradation when utilization columns absent |

> Tier 2 cost figures are computed estimates from a documented instance-matching methodology, not observed billing invoices.

---

## API Reference

```
Authentication
  POST /api/v1/auth/signup        Create organization + admin user
  POST /api/v1/auth/login         Issue JWT token

Dashboard
  GET  /api/v1/dashboard          KPIs (Redis cache → Postgres fallback)
  GET  /api/v1/business-metrics   Resume metrics (savings, coverage, confidence)

ML Outputs
  GET  /api/v1/forecast           Hierarchical forecasts + naive baselines
  GET  /api/v1/anomalies          Flagged resources with dimension scores
  GET  /api/v1/waste              Waste classifications + SHAP features
  GET  /api/v1/recommendations    Ranked recommendations + confidence scores

AI Layer
  POST /api/v1/copilot            NL question → grounded answer + citations
  GET  /api/v1/insights/active    Executive insight for active dataset
  POST /api/v1/insights/generate  Regenerate insight (analyst+ only)

Dataset Management
  POST /api/v1/datasets/upload    Upload CSV with analysis mode
  GET  /api/v1/datasets           Analysis history
  GET  /api/v1/datasets/active    Current active dataset
  POST /api/v1/datasets/{id}/activate  Switch active dataset
  POST /api/v1/datasets/reset     Safe reset with confirmation

Simulator
  POST /api/v1/simulate           What-if cost impact of termination/resize

Models
  GET  /api/v1/models/registry    Model versions + evaluation metrics
  POST /api/v1/models/retrain     Manual retrain trigger (admin only)

Reports
  GET  /api/v1/reports/weekly     Executive report history
```

Full interactive docs at `/api/v1/docs` (Swagger UI).

---

## Local Setup

### Prerequisites

- Python 3.11+
- Node.js 20+
- [Neon](https://neon.tech) account (free)
- [Upstash](https://upstash.com) Redis account (free)
- [Groq](https://console.groq.com) API key (free) and/or [Gemini](https://aistudio.google.com/app/apikey) API key (free)

### Step 1 — Clone and configure

```bash
git clone https://github.com/Ayush8092/CostGuard-AI.git
cd CostGuard-AI
cp .env.example .env
```

Edit `.env` — only these four values need changing:

```env
DATABASE_URL_OVERRIDE=postgresql+psycopg2://user:pass@ep-xxxx.neon.tech/costguard?sslmode=require
REDIS_URL_OVERRIDE=redis://default:pass@amazed-xxxx.upstash.io:6379
GROQ_API_KEY=gsk_...
GEMINI_API_KEY=AI...
```

### Step 2 — Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

pip install -r requirements.txt
alembic upgrade head
python -m app.workers.seed_data        # creates demo org + loads synthetic data
python -m app.workers.nightly_job      # trains models + runs first inference
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Step 3 — Frontend

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**

**Demo credentials** (after seeding):
```
Email:    admin@costguard.demo
Password: CostGuard2024!
```

### Step 4 — Load test (optional)

```bash
cd backend
pip install locust
locust -f tests/locustfile.py \
  --host http://localhost:8000 \
  --users 200 --spawn-rate 10 \
  --run-time 60s --headless \
  --csv load_test_results --html load_test_report.html
```

---

## Project Structure

```
costguard/
├── backend/
│   ├── app/
│   │   ├── api/routes/          # 28 FastAPI endpoints across 12 route modules
│   │   ├── core/                # Config, JWT auth, Redis cache, rate limiting
│   │   ├── data/                # Tiers 1–3: synthetic, Bitbrains, CSV upload
│   │   ├── db/                  # SQLAlchemy models (11 tables) + Alembic migrations
│   │   ├── features/            # Feature engineering + PostgreSQL feature store
│   │   ├── llm/                 # Copilot, Advisor, Simulator, Weekly Report, LLM client
│   │   ├── mlops/               # PSI + KS drift detection, model registry
│   │   ├── models/              # Forecasting, anomaly detection, waste, SHAP, scoring
│   │   ├── rag/                 # FAISS knowledge base (58 chunks) + instance lookup
│   │   ├── training/            # Separated training pipelines (forecast, anomaly, waste)
│   │   └── workers/             # Nightly inference, scheduler, CSV processor, seed data
│   ├── migrations/versions/     # Alembic migrations 0001–0005
│   ├── tests/                   # Locust load test + summarizer
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/                 # Axios client with JWT interceptor
│   │   ├── components/          # AppShell, StatusBar, AnalysisHistory, KpiCard, ConfidenceBadge
│   │   ├── context/             # AuthContext, DatasetContext
│   │   └── pages/               # 10 tab pages
│   └── package.json
├── architecture_diagram.svg
├── infographic_diagram.svg
├── User_Workflow.png
├── .env.example
└── docker-compose.yml
```

---

## Design Decisions

**Why XGBoost over Prophet?**
Prophet requires a Stan compiler toolchain, which adds significant install weight. XGBoost quantile regression delivers equivalent confidence intervals from one library that is already required for the waste classifier, keeping `docker compose up` lightweight.

**Why SHAP computed at inference time, not on request?**
Computing SHAP on every user request at 200 concurrent users would be prohibitively expensive. SHAP values are computed once during the nightly inference pass and stored in the `waste_classifications` table. Dashboard requests read pre-computed values — zero ML compute on the hot path.

**Why `LLM_PROVIDER=auto` instead of forcing one provider?**
Both Gemini and Groq have free-tier rate limits that can be exhausted under real usage. The auto-fallback mode means neither provider's limit kills the application — Gemini serves until quota is hit, Groq takes over silently.

**Why separate training from inference?**
The nightly job runs inference only (fast, cheap). Training runs only when actually needed: first run, drift detected, weekly schedule, or admin trigger. This is production FinOps practice — retraining every night wastes compute and can degrade models if the new data window is too small.

---

## Infrastructure

| Component | Provider | Cost |
|-----------|----------|------|
| Backend hosting | Railway | Free hobby plan |
| PostgreSQL | Neon | Free tier (10GB) |
| Redis cache | Upstash | Free tier (10K req/day) |
| LLM (primary) | Gemini via Google AI Studio | Free tier |
| LLM (fallback) | Groq | Free tier |
| Frontend | Vercel | Free hobby plan |
| Embeddings | all-MiniLM-L6-v2 (local) | $0 |
| Vector search | FAISS CPU | $0 |

**Total monthly infrastructure cost: $0**

---

## What Is Explicitly Out of Scope

Per the project specification:

- **Live AWS Cost Explorer** connector (v2 roadmap — requires read-only IAM role, never raw access keys)
- **Claimed accuracy on real-world data** — anomaly detection runs unsupervised on real data; no F1 score is reported for uploads
- **AI Incident Analyzer** — separate portfolio project
- **Fabricated metrics** — every number in this README traces to a verifiable formula or model output

---

## License

MIT — free to use, modify, and deploy.

---

<div align="center">

Built by [Ayush Kumar](https://github.com/Ayush8092) · [LinkedIn](https://linkedin.com/in/your-profile) · [ak1357kumar@gmail.com](mailto:ak1357kumar@gmail.com)

*If this project helped you, a star would be appreciated.*

</div>

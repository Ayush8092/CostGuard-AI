"""
Main FastAPI application entrypoint.
"""
from __future__ import annotations
import os
import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api.routes import (
    anomalies, auth, business_metrics, copilot,
    dashboard, forecast, monitoring, recommendations,
    reports, simulator, upload, waste,
)
from app.api.routes import datasets, insights   # new in Feature 1-4
from app.core.config import get_settings
from app.workers.scheduler import start_scheduler

settings = get_settings()
app = FastAPI(title=settings.APP_NAME, version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    ms = round((time.perf_counter() - start) * 1000, 2)
    logger.info(f"{request.method} {request.url.path} -> {response.status_code} ({ms}ms)")
    return response

@app.on_event("startup")
def on_startup() -> None:
    start_scheduler()

@app.get("/health")
def health():
    return {"status": "ok", "service": settings.APP_NAME}

@app.get("/health/db")
def health_db():
    from sqlalchemy import text
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "component": "postgres"}
    except Exception as e:
        return {"status": "error", "component": "postgres", "detail": str(e)}
    finally:
        db.close()

@app.get("/health/redis")
def health_redis():
    from app.core.cache import get_redis_or_none
    client = get_redis_or_none()
    if client:
        return {"status": "ok", "component": "redis"}
    return {"status": "error", "component": "redis", "detail": "unavailable"}

api = settings.API_V1_PREFIX
app.include_router(auth.router,             prefix=api)
app.include_router(dashboard.router,        prefix=api)
app.include_router(forecast.router,         prefix=api)
app.include_router(anomalies.router,        prefix=api)
app.include_router(waste.router,            prefix=api)
app.include_router(recommendations.router,  prefix=api)
app.include_router(simulator.router,        prefix=api)
app.include_router(copilot.router,          prefix=api)
app.include_router(reports.router,          prefix=api)
app.include_router(monitoring.router,       prefix=api)
app.include_router(upload.router,           prefix=api)
app.include_router(business_metrics.router, prefix=api)
app.include_router(datasets.router,         prefix=api)   # Feature 1+2+4
app.include_router(insights.router,         prefix=api)   # Feature 3

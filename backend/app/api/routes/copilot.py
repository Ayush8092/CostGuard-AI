"""
Copilot route - wraps every failure point in try/except so the endpoint
never returns a raw 500. Returns a structured error with detail instead.

Failure points handled individually:
  1. Redis rate limit (fail-open if Redis down)
  2. DB data loading (returns empty dataframes, Copilot handles gracefully)
  3. FAISS knowledge base (skipped if unavailable)
  4. Gemini API failure (LLM client falls back to Groq or stub)
  5. Any unhandled exception (caught at the top level, returns 200 with error detail)
"""
from __future__ import annotations

import traceback
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.core.rate_limit import llm_rate_limit
from app.db.models import ForecastResult, ProcessedTelemetry, WasteClassification
from app.db.session import get_db
from app.llm.copilot import FinOpsCopilot
from loguru import logger

router = APIRouter(prefix="/copilot", tags=["copilot"])


class CopilotRequest(BaseModel):
    question: str


class CitationOut(BaseModel):
    chunk_id: str
    title: str
    similarity_score: float


class CopilotResponseOut(BaseModel):
    answer: str
    intent: str
    citations: list[CitationOut]
    tool_trace: list[str]
    is_stub: bool


def _load_org_dataframes(db: Session, org_id: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load billing, waste, and forecast data. Returns empty dataframes on any error."""
    billing_df = pd.DataFrame()
    waste_df = pd.DataFrame()
    forecast_df = pd.DataFrame()

    try:
        rows = db.query(ProcessedTelemetry).filter(
            ProcessedTelemetry.organization_id == org_id
        ).all()
        if rows:
            billing_df = pd.DataFrame([{
                "date": r.date, "resource_id": r.resource_id, "service": r.service,
                "cost": r.cost, "cpu_avg_pct": r.cpu_avg_pct,
                "memory_avg_pct": r.memory_avg_pct, "network_io": r.network_io,
                "disk_io": r.disk_io, "region": r.region,
            } for r in rows])
    except Exception as e:
        logger.warning(f"Copilot: failed to load billing data for org {org_id}: {e}")

    try:
        waste_rows = db.query(WasteClassification).filter(
            WasteClassification.organization_id == org_id
        ).all()
        if waste_rows:
            waste_df = pd.DataFrame([{
                "resource_id": r.resource_id, "date": r.date,
                "waste_score": r.waste_score, "bucket": r.bucket,
                "cpu_avg_pct": None,
            } for r in waste_rows])
    except Exception as e:
        logger.warning(f"Copilot: failed to load waste data for org {org_id}: {e}")

    try:
        forecast_rows = db.query(ForecastResult).filter(
            ForecastResult.organization_id == org_id
        ).all()
        if forecast_rows:
            forecast_df = pd.DataFrame([{
                "service": r.service, "forecast": r.forecast,
                "ci_lower": r.ci_lower, "ci_upper": r.ci_upper,
            } for r in forecast_rows])
    except Exception as e:
        logger.warning(f"Copilot: failed to load forecast data for org {org_id}: {e}")

    return billing_df, waste_df, forecast_df


def _get_knowledge_base():
    """Returns FAISS knowledge base or None if unavailable."""
    try:
        from app.rag.faiss_store import get_knowledge_base
        return get_knowledge_base()
    except Exception as e:
        logger.warning(f"Copilot: FAISS knowledge base unavailable: {e}")
        return None


@router.post("", response_model=CopilotResponseOut)
def ask_copilot(
    payload: CopilotRequest,
    current_user: CurrentUser = Depends(llm_rate_limit),
    db: Session = Depends(get_db),
) -> CopilotResponseOut:

    if not payload.question or not payload.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        billing_df, waste_df, forecast_df = _load_org_dataframes(db, current_user.organization_id)
        kb = _get_knowledge_base()
        copilot = FinOpsCopilot(knowledge_base=kb)

        result = copilot.answer(
            question=payload.question,
            billing_df=billing_df if not billing_df.empty else None,
            waste_scored_df=waste_df if not waste_df.empty else None,
            forecast_df=forecast_df if not forecast_df.empty else None,
        )

        return CopilotResponseOut(
            answer=result.answer_text,
            intent=result.intent.value,
            citations=[
                CitationOut(
                    chunk_id=c.chunk.chunk_id,
                    title=c.chunk.title,
                    similarity_score=round(c.similarity_score, 4),
                )
                for c in result.citations
            ],
            tool_trace=result.tool_trace,
            is_stub=result.is_stub,
        )

    except HTTPException:
        raise  # re-raise 429 rate limit responses

    except Exception as e:
        # Log the full traceback for debugging but return a clean response
        logger.error(f"Copilot error for org {current_user.organization_id}: {e}\n{traceback.format_exc()}")
        # Return a 200 with an error answer rather than a 500, so the
        # frontend CopilotResponseOut model still parses successfully.
        return CopilotResponseOut(
            answer=f"I encountered an error processing your question: {str(e)[:200]}. "
                   f"This is likely a temporary issue. Please try again in a moment.",
            intent="general_question",
            citations=[],
            tool_trace=[f"error: {str(e)[:100]}"],
            is_stub=False,
        )

"""
AI FinOps Copilot (Part 4.1).

Pipeline: NL Question -> Intent Detection -> Query structured data
-> Retrieve FAISS knowledge -> Grounded answer with citations.

Every handler wraps its data access in try/except so one bad value
(None, NaN, missing column) never crashes the entire request.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum

import pandas as pd

from app.llm.client import GROUNDING_SYSTEM_PROMPT, LlmClient
from app.rag.faiss_store import FaissKnowledgeBase, RetrievedChunk


class Intent(str, Enum):
    BILL_INCREASE_EXPLANATION = "bill_increase_explanation"
    TERMINATION_CANDIDATES    = "termination_candidates"
    IDLE_RESOURCES            = "idle_resources"
    PERIOD_COMPARISON         = "period_comparison"
    HIGHEST_METRIC_RESOURCE   = "highest_metric_resource"
    FORECAST_REQUEST          = "forecast_request"
    GENERAL_QUESTION          = "general_question"


@dataclass
class IntentMatch:
    intent: Intent
    extracted_params: dict = field(default_factory=dict)


_INTENT_PATTERNS: list[tuple[str, Intent]] = [
    (r"why.*(bill|cost|spend).*(increase|went up|higher|jump)",       Intent.BILL_INCREASE_EXPLANATION),
    (r"(which|what).*(instance|resource|vm).*(terminate|shut|remove)", Intent.TERMINATION_CANDIDATES),
    (r"(show|list|find).*(idle|unused|underutilized)",                 Intent.IDLE_RESOURCES),
    (r"compare.*(last|previous).*(month|week).*(this|current)",        Intent.PERIOD_COMPARISON),
    (r"(which|what).*(highest|most|top).*(network|cpu|memory|disk)",   Intent.HIGHEST_METRIC_RESOURCE),
    (r"forecast.*(cost|spend)",                                        Intent.FORECAST_REQUEST),
]

_REGION_PATTERN  = re.compile(r"\b(us|eu|ap|sa|ca)-[a-z]+-\d\b")
_SERVICE_PATTERN = re.compile(r"\b(EC2|S3|RDS|Lambda)\b", re.IGNORECASE)
_METRIC_PATTERN  = re.compile(r"\b(network|cpu|memory|disk)\b", re.IGNORECASE)

_METRIC_TO_COLUMN = {
    "network": "network_io",
    "cpu":     "cpu_avg_pct",
    "memory":  "memory_avg_pct",
    "disk":    "disk_io",
}


def detect_intent(question: str) -> IntentMatch:
    q = question.lower()
    for pattern, intent in _INTENT_PATTERNS:
        if re.search(pattern, q):
            params = {}
            if m := _REGION_PATTERN.search(q):
                params["region"] = m.group(0)
            if m := _SERVICE_PATTERN.search(question):
                params["service"] = m.group(0).upper()
            if m := _METRIC_PATTERN.search(q):
                params["metric"] = m.group(0).lower()
            return IntentMatch(intent=intent, extracted_params=params)
    return IntentMatch(intent=Intent.GENERAL_QUESTION)


# ── Intent handlers ───────────────────────────────────────────────────────

def _safe_float(value) -> float | None:
    """Convert a value to float safely, returning None for null/NaN."""
    try:
        import math
        v = float(value)
        return None if math.isnan(v) or math.isinf(v) else v
    except (TypeError, ValueError):
        return None


def _handle_bill_increase(df: pd.DataFrame, params: dict) -> dict:
    try:
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])
        max_date = df["date"].max()
        last_30 = df[df["date"] >= max_date - pd.Timedelta(days=30)]
        prev_30 = df[
            (df["date"] < max_date - pd.Timedelta(days=30)) &
            (df["date"] >= max_date - pd.Timedelta(days=60))
        ]
        this_total = float(last_30["cost"].sum())
        prev_total = float(prev_30["cost"].sum())
        pct = round((this_total / max(prev_total, 1e-6) - 1) * 100, 2)
        by_svc = last_30.groupby("service")["cost"].sum()
        return {
            "total_cost_last_30d":  round(this_total, 2),
            "total_cost_prev_30d":  round(prev_total, 2),
            "pct_change":           pct,
            "top_service_increases": {
                k: round(float(v), 2)
                for k, v in (by_svc - prev_30.groupby("service")["cost"].sum())
                .fillna(0).sort_values(ascending=False).head(3).items()
            },
        }
    except Exception as e:
        return {"error": f"Could not compute bill increase: {e}"}


def _handle_termination_candidates(waste_df: pd.DataFrame, top_n: int = 5) -> dict:
    try:
        candidates = waste_df[waste_df["bucket"].isin(["Critical Waste", "Idle"])]
        candidates = candidates.sort_values("waste_score", ascending=False).head(top_n)
        return {
            "candidates": candidates[
                [c for c in ["resource_id", "waste_score", "bucket", "cpu_avg_pct"] if c in candidates.columns]
            ].round(2).to_dict("records")
        }
    except Exception as e:
        return {"error": f"Could not find termination candidates: {e}"}


def _handle_idle_resources(waste_df: pd.DataFrame, params: dict) -> dict:
    try:
        idle = waste_df[waste_df["bucket"].isin(["Idle", "Critical Waste"])]
        return {
            "idle_resource_count": int(idle["resource_id"].nunique()),
            "resources": idle.drop_duplicates("resource_id").head(20)[
                [c for c in ["resource_id", "bucket", "waste_score"] if c in idle.columns]
            ].round(2).to_dict("records"),
        }
    except Exception as e:
        return {"error": f"Could not list idle resources: {e}"}


def _handle_period_comparison(df: pd.DataFrame) -> dict:
    try:
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])
        max_date = df["date"].max()
        this = df[df["date"] >= max_date - pd.Timedelta(days=30)]
        prev = df[
            (df["date"] < max_date - pd.Timedelta(days=30)) &
            (df["date"] >= max_date - pd.Timedelta(days=60))
        ]
        this_total = round(float(this["cost"].sum()), 2)
        prev_total = round(float(prev["cost"].sum()), 2)
        return {
            "this_period_cost": this_total,
            "last_period_cost": prev_total,
            "difference":       round(this_total - prev_total, 2),
        }
    except Exception as e:
        return {"error": f"Could not compare periods: {e}"}


def _handle_highest_metric_resource(df: pd.DataFrame, params: dict) -> dict:
    try:
        metric_key = params.get("metric", "cpu")
        metric_col = _METRIC_TO_COLUMN.get(metric_key, "cpu_avg_pct")

        if metric_col not in df.columns:
            return {"error": f"Column '{metric_col}' not available in this dataset."}

        # Drop rows where the metric is null — common for S3/Lambda which
        # have no CPU/memory data in the same dataset as EC2/RDS resources.
        valid = df[df[metric_col].notna()]
        if valid.empty:
            return {"error": f"No valid (non-null) values found for '{metric_col}' in the current dataset."}

        top = valid.sort_values(metric_col, ascending=False).iloc[0]
        value = _safe_float(top[metric_col])
        if value is None:
            return {"error": f"Could not read '{metric_col}' value for resource '{top.get('resource_id', 'unknown')}'."}

        return {
            "resource_id": str(top["resource_id"]),
            "metric":      metric_col,
            "value":       round(value, 2),
            "date":        str(top.get("date", "unknown")),
        }
    except Exception as e:
        return {"error": f"Could not find highest {params.get('metric','cpu')} resource: {e}"}


def _handle_forecast_request(forecast_df: pd.DataFrame, params: dict) -> dict:
    try:
        service = params.get("service")
        relevant = (
            forecast_df[forecast_df["service"] == service]
            if service and "service" in forecast_df.columns
            else forecast_df
        )
        if relevant.empty:
            return {"error": "No forecast available for the requested scope. Run the nightly job first."}
        row = relevant.iloc[0]
        return {
            "forecast":  round(float(row["forecast"]), 2),
            "ci_lower":  round(float(row["ci_lower"]), 2),
            "ci_upper":  round(float(row["ci_upper"]), 2),
            "service":   service or "org_total",
        }
    except Exception as e:
        return {"error": f"Could not retrieve forecast: {e}"}


# ── Copilot class ─────────────────────────────────────────────────────────

@dataclass
class CopilotAnswer:
    answer_text: str
    intent: Intent
    structured_context: dict
    citations: list[RetrievedChunk]
    tool_trace: list[str]
    is_stub: bool


class FinOpsCopilot:
    def __init__(
        self,
        knowledge_base: FaissKnowledgeBase | None = None,
        llm_client: LlmClient | None = None,
    ):
        self.kb  = knowledge_base
        self.llm = llm_client or LlmClient()

    def answer(
        self,
        question: str,
        billing_df:     pd.DataFrame | None = None,
        waste_scored_df: pd.DataFrame | None = None,
        forecast_df:    pd.DataFrame | None = None,
    ) -> CopilotAnswer:
        tool_trace = [f"intent_detection(question={question!r})"]
        match = detect_intent(question)
        tool_trace.append(f"intent={match.intent.value} params={match.extracted_params}")

        structured_context: dict = {}

        try:
            if match.intent == Intent.BILL_INCREASE_EXPLANATION and billing_df is not None:
                tool_trace.append("query_billing_data(window=60d)")
                structured_context = _handle_bill_increase(billing_df, match.extracted_params)

            elif match.intent == Intent.TERMINATION_CANDIDATES and waste_scored_df is not None:
                tool_trace.append("query_waste_classifications(bucket__in=[Critical Waste,Idle])")
                structured_context = _handle_termination_candidates(waste_scored_df)

            elif match.intent == Intent.IDLE_RESOURCES and waste_scored_df is not None:
                tool_trace.append("query_waste_classifications(bucket__in=[Idle,Critical Waste])")
                structured_context = _handle_idle_resources(waste_scored_df, match.extracted_params)

            elif match.intent == Intent.PERIOD_COMPARISON and billing_df is not None:
                tool_trace.append("query_billing_data(compare=last_vs_this_30d)")
                structured_context = _handle_period_comparison(billing_df)

            elif match.intent == Intent.HIGHEST_METRIC_RESOURCE and billing_df is not None:
                tool_trace.append(f"query_billing_data(sort={match.extracted_params.get('metric','cpu')}_desc)")
                structured_context = _handle_highest_metric_resource(billing_df, match.extracted_params)

            elif match.intent == Intent.FORECAST_REQUEST and forecast_df is not None:
                tool_trace.append("query_forecast_results()")
                structured_context = _handle_forecast_request(forecast_df, match.extracted_params)

            else:
                structured_context = {"note": "No structured data matched this query — answering from knowledge base only."}

        except Exception as e:
            structured_context = {"error": f"Data retrieval failed: {e}"}
            tool_trace.append(f"data_error: {e}")

        # FAISS retrieval
        citations: list[RetrievedChunk] = []
        if self.kb is not None:
            try:
                tool_trace.append("faiss_retrieve(top_k=3)")
                citations = self.kb.retrieve(question, top_k=3)
            except Exception as e:
                tool_trace.append(f"faiss_error: {e}")

        # Build prompt and call LLM
        user_prompt = self._build_prompt(question, structured_context, citations)
        try:
            llm_response = self.llm.complete(
                system_prompt=GROUNDING_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
            tool_trace.append(f"llm_complete(provider={llm_response.provider})")
        except Exception as e:
            tool_trace.append(f"llm_error: {e}")
            from app.llm.client import LlmResponse
            llm_response = LlmResponse(
                text=f"I retrieved the data successfully but encountered an LLM error: {e}. "
                     f"Here is the raw context: {json.dumps(structured_context, default=str)[:400]}",
                provider="error",
                model="none",
                is_stub=True,
            )

        return CopilotAnswer(
            answer_text=llm_response.text,
            intent=match.intent,
            structured_context=structured_context,
            citations=citations,
            tool_trace=tool_trace,
            is_stub=llm_response.is_stub,
        )

    @staticmethod
    def _build_prompt(
        question: str,
        structured_context: dict,
        citations: list[RetrievedChunk],
    ) -> str:
        parts = [f"User question: {question}", ""]
        if structured_context:
            parts.append("Structured data (ONLY numbers you may reference):")
            parts.append(json.dumps(structured_context, indent=2, default=str))
        else:
            parts.append("No structured data matched this question.")
        if citations:
            parts.append("\nRelevant best-practice guidance (cite by chunk_id if used):")
            for c in citations:
                parts.append(f"  [{c.chunk.chunk_id}] {c.chunk.title}: {c.chunk.content}")
        return "\n".join(parts)

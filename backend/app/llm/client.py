"""
LLM client abstraction (Part 4).

All LLM calls receive ONLY structured JSON/text from ML model outputs
or DB queries - never raw telemetry, and the system prompt explicitly
instructs the model not to invent numbers. This module is the single
place that talks to the actual LLM provider, so swapping providers
(Groq <-> Gemini) never touches the Copilot/Advisor/Report logic.

Supports:
  - "groq": Groq's free-tier API only (Llama models, very fast inference)
  - "gemini": Google AI Studio free-tier API only
  - "auto": tries Gemini first; if Gemini's free-tier rate limit is hit,
            transparently falls back to Groq for that request. The
            caller (Copilot/Advisor/Report) and the end user never see
            which provider actually answered - the response shape is
            identical either way. Falls back ONLY on rate-limit/quota
            errors, never on other failures (e.g. a genuine API outage
            or bad request should surface, not be silently masked).
  - "none": stub mode - returns a clearly-labeled placeholder response
            instead of calling any provider, so the rest of the app is
            fully testable/runnable with zero API keys configured.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_settings

GROUNDING_SYSTEM_PROMPT = (
    "You are the CostGuard AI FinOps Copilot. You will be given structured data "
    "(JSON from ML models or database queries). You must ONLY reference numbers, "
    "dates, and resource names that appear explicitly in the provided context. "
    "Never invent, estimate, or guess at any numeric value that is not present in "
    "the context. If the context does not contain enough information to answer "
    "the question, say so explicitly rather than filling the gap with a plausible "
    "sounding number. Cite which piece of context supports each claim you make."
)

# Substrings that reliably appear in rate-limit / quota-exceeded errors from
# each provider's SDK. Used to detect "this was a quota problem, fall back"
# versus "this was a real error, let it surface" without depending on
# brittle exact exception types that can change between SDK versions.
_RATE_LIMIT_SIGNALS = ("rate limit", "quota", "resource_exhausted", "429", "too many requests")


def _is_rate_limit_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(signal in message for signal in _RATE_LIMIT_SIGNALS)


@dataclass
class LlmResponse:
    text: str
    provider: str
    model: str
    is_stub: bool = False


class LlmClient:
    def __init__(self):
        self.settings = get_settings()

    def complete(self, system_prompt: str, user_prompt: str, max_tokens: int = 800) -> LlmResponse:
        provider = self.settings.LLM_PROVIDER

        if provider == "auto":
            return self._complete_auto(system_prompt, user_prompt, max_tokens)
        if provider == "groq":
            return self._complete_groq(system_prompt, user_prompt, max_tokens)
        if provider == "gemini":
            return self._complete_gemini(system_prompt, user_prompt, max_tokens)
        return self._complete_stub(system_prompt, user_prompt)

    def _complete_auto(self, system_prompt: str, user_prompt: str, max_tokens: int) -> LlmResponse:
        """
        Gemini-first with a silent fallback to Groq on rate-limit errors.
        The returned LlmResponse.provider field still reports which
        provider actually answered (useful for logs/debugging), but
        nothing about the response TEXT or shape differs based on which
        one served it - the Copilot/Advisor/Report code and the frontend
        UI never branch on this, so the user experience is identical.
        """
        if self.settings.GEMINI_API_KEY:
            try:
                return self._complete_gemini(system_prompt, user_prompt, max_tokens)
            except Exception as e:  # noqa: BLE001 - intentionally broad, filtered by _is_rate_limit_error below
                if not _is_rate_limit_error(e):
                    raise  # a non-quota error (bad request, outage, etc.) should surface, not be hidden
                # fall through to Groq below

        if self.settings.GROQ_API_KEY:
            return self._complete_groq(system_prompt, user_prompt, max_tokens)

        return self._complete_stub(system_prompt, user_prompt, note="no API key available for auto mode")

    def _complete_groq(self, system_prompt: str, user_prompt: str, max_tokens: int) -> LlmResponse:
        from groq import Groq

        if not self.settings.GROQ_API_KEY:
            return self._complete_stub(system_prompt, user_prompt, note="GROQ_API_KEY not set")

        client = Groq(api_key=self.settings.GROQ_API_KEY)
        completion = client.chat.completions.create(
            model=self.settings.GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.2,  # low temperature - this is a grounded, factual reporting task, not creative writing
        )
        text = completion.choices[0].message.content
        return LlmResponse(text=text, provider="groq", model=self.settings.GROQ_MODEL)

    def _complete_gemini(self, system_prompt: str, user_prompt: str, max_tokens: int) -> LlmResponse:
        import google.generativeai as genai

        if not self.settings.GEMINI_API_KEY:
            return self._complete_stub(system_prompt, user_prompt, note="GEMINI_API_KEY not set")

        genai.configure(api_key=self.settings.GEMINI_API_KEY)
        model = genai.GenerativeModel(self.settings.GEMINI_MODEL, system_instruction=system_prompt)
        response = model.generate_content(
            user_prompt,
            generation_config=genai.types.GenerationConfig(max_output_tokens=max_tokens, temperature=0.2),
        )
        return LlmResponse(text=response.text, provider="gemini", model=self.settings.GEMINI_MODEL)

    def _complete_stub(self, system_prompt: str, user_prompt: str, note: str = "") -> LlmResponse:
        """
        Stub mode - used when LLM_PROVIDER=none or no API key is
        available. Returns a clearly-labeled placeholder so the app
        remains fully runnable and demoable with zero LLM cost/setup,
        while making it obvious in the UI that this is not a real
        model response.
        """
        suffix = f" ({note})" if note else ""
        text = (
            f"[STUB LLM RESPONSE{suffix} - configure GROQ_API_KEY and/or GEMINI_API_KEY in .env "
            f"to get real grounded answers]\n\n"
            f"Context received:\n{user_prompt[:500]}"
        )
        return LlmResponse(text=text, provider="stub", model="none", is_stub=True)


if __name__ == "__main__":
    client = LlmClient()
    response = client.complete(
        system_prompt=GROUNDING_SYSTEM_PROMPT,
        user_prompt="Forecast data: {\"forecast\": 120.5, \"ci_lower\": 110.2, \"ci_upper\": 131.8}. "
                    "Question: what is the forecasted cost?",
    )
    print(f"Provider: {response.provider}, Model: {response.model}, Is stub: {response.is_stub}")
    print(response.text)
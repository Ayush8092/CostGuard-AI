"""
Rate limiting for LLM endpoints using Redis sliding window.

If Redis is unavailable, requests are ALLOWED through (fail-open).
This is the correct behavior: a Redis outage should not block users
from using the AI Copilot. The free-tier LLM quota is the backstop.
"""
from __future__ import annotations
from fastapi import Depends, HTTPException, status
from app.api.deps import CurrentUser, get_current_user
from app.core.cache import redis_incr, redis_expire
from app.core.config import get_settings


def llm_rate_limit(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    settings = get_settings()
    key = f"llm_rate_limit:{current_user.id}"

    try:
        count = redis_incr(key)
        if count is None:
            # Redis unavailable - allow the request through (fail-open)
            return current_user
        if count == 1:
            # First request in this window - set the 60s expiry
            redis_expire(key, 60)
        if count > settings.LLM_RATE_LIMIT_PER_MINUTE:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded: max {settings.LLM_RATE_LIMIT_PER_MINUTE} AI requests per minute.",
            )
    except HTTPException:
        raise  # re-raise 429, don't swallow it
    except Exception:
        pass  # any other Redis error - allow through

    return current_user

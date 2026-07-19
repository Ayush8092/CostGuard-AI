"""
Redis client - single connection point for the entire app.

Upstash shows redis:// in their dashboard but REQUIRES TLS.
This module automatically upgrades redis:// to rediss:// for Upstash URLs
so you can paste the URL exactly from the Upstash dashboard into .env.

Rule: every module that uses Redis MUST call get_redis_or_none().
Never call get_redis_client() directly outside this file - it can raise
on connection failure and crash the request.
"""
from __future__ import annotations
from functools import lru_cache
import redis
from app.core.config import get_settings


def _build_redis_url(url: str) -> str:
    """
    Upstash always requires TLS even though their dashboard shows redis://.
    Detect Upstash by hostname and force rediss:// so the connection works
    regardless of what the dashboard copy-paste gives you.
    """
    if not url:
        return url
    # Force TLS for Upstash (upstash.io domains always need it)
    if "upstash.io" in url and url.startswith("redis://"):
        url = "rediss://" + url[len("redis://"):]
    return url


@lru_cache(maxsize=1)
def get_redis_client() -> redis.Redis:
    settings = get_settings()
    url = _build_redis_url(settings.REDIS_URL)
    # ssl_cert_reqs=None skips certificate verification which is needed
    # for Upstash's self-signed cert on the free tier.
    if url.startswith("rediss://"):
        return redis.from_url(url, decode_responses=True, ssl_cert_reqs=None)
    return redis.from_url(url, decode_responses=True)


def get_redis_or_none() -> redis.Redis | None:
    """
    THE ONLY function every other module should call.
    Returns a working Redis client, or None if Redis is unavailable.
    None means: skip the cache, continue without Redis, never crash.
    """
    try:
        client = get_redis_client()
        client.ping()
        return client
    except Exception:
        return None


def redis_get(key: str) -> str | None:
    """Safe get - returns None on any error."""
    try:
        client = get_redis_or_none()
        if client is None:
            return None
        return client.get(key)
    except Exception:
        return None


def redis_set(key: str, value: str, ttl_seconds: int = 3600) -> bool:
    """Safe set - returns False on any error, never raises."""
    try:
        client = get_redis_or_none()
        if client is None:
            return False
        client.setex(key, ttl_seconds, value)
        return True
    except Exception:
        return False


def redis_delete(key: str) -> bool:
    """Safe delete - returns False on any error."""
    try:
        client = get_redis_or_none()
        if client is None:
            return False
        client.delete(key)
        return True
    except Exception:
        return False


def redis_incr(key: str) -> int | None:
    """Safe incr - returns None on any error."""
    try:
        client = get_redis_or_none()
        if client is None:
            return None
        return client.incr(key)
    except Exception:
        return None


def redis_expire(key: str, seconds: int) -> bool:
    """Safe expire - returns False on any error."""
    try:
        client = get_redis_or_none()
        if client is None:
            return False
        client.expire(key, seconds)
        return True
    except Exception:
        return False

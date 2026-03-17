"""Redis client for caching and rate limiting.

Uses REDIS_URL env var (e.g. redis://10.0.0.3:6379).
Falls back gracefully to in-memory dicts when Redis is unavailable.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from shared.logger import get_logger

logger = get_logger("redis_client")

_redis: Any = None
_init_attempted = False


def _get_redis():
    """Lazy-init Redis connection. Returns None if unavailable."""
    global _redis, _init_attempted

    if _init_attempted:
        return _redis

    _init_attempted = True
    url = os.getenv("REDIS_URL")
    if not url:
        logger.info("redis.disabled", extra={"reason": "REDIS_URL not set"})
        return None

    try:
        import redis as redis_lib

        _redis = redis_lib.Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=2,
            retry_on_timeout=True,
        )
        _redis.ping()
        logger.info("redis.connected", extra={"url": url.split("@")[-1]})
    except Exception as exc:
        logger.warning("redis.connection_failed", extra={"error": str(exc)})
        _redis = None

    return _redis


# ── Cache helpers ────────────────────────────────────────────────────────────

_local_cache: dict[str, tuple[Any, float]] = {}


def cache_get(key: str) -> Any | None:
    """Get a cached value. Tries Redis first, falls back to local memory."""
    r = _get_redis()
    if r:
        try:
            val = r.get(key)
            return json.loads(val) if val else None
        except Exception:
            pass

    entry = _local_cache.get(key)
    if entry:
        value, expires_at = entry
        if time.monotonic() < expires_at:
            return value
        del _local_cache[key]
    return None


def cache_set(key: str, value: Any, ttl_seconds: int = 300) -> None:
    """Cache a value with TTL. Writes to Redis and local memory."""
    r = _get_redis()
    if r:
        try:
            r.setex(key, ttl_seconds, json.dumps(value, default=str))
        except Exception:
            pass

    _local_cache[key] = (value, time.monotonic() + ttl_seconds)


def cache_delete(key: str) -> None:
    """Remove a cached value."""
    r = _get_redis()
    if r:
        try:
            r.delete(key)
        except Exception:
            pass

    _local_cache.pop(key, None)


def cache_delete_pattern(pattern: str) -> None:
    """Remove all keys matching a pattern (e.g. 'tenant:abc*')."""
    r = _get_redis()
    if r:
        try:
            cursor = 0
            while True:
                cursor, keys = r.scan(cursor, match=pattern, count=100)
                if keys:
                    r.delete(*keys)
                if cursor == 0:
                    break
        except Exception:
            pass

    # Local cache: match by prefix (simple glob)
    prefix = pattern.rstrip("*")
    to_delete = [k for k in _local_cache if k.startswith(prefix)]
    for k in to_delete:
        del _local_cache[k]


# ── Usage counters ────────────────────────────────────────────────────────────

_in_memory_counters: dict[str, int] = {}


def counter_increment(key: str, ttl_seconds: int = 172800) -> int:
    """Atomically increment a Redis counter. Returns new value.

    Falls back to in-memory dict when Redis is unavailable.
    TTL defaults to 48 hours.
    """
    client = _get_redis()
    if client is not None:
        try:
            pipe = client.pipeline()
            pipe.incr(key)
            pipe.expire(key, ttl_seconds)
            results = pipe.execute()
            return int(results[0])
        except Exception as exc:
            logger.warning("redis.counter_increment_failed", extra={"key": key, "error": str(exc)})
    # In-memory fallback (resets on deploy — fail-open is acceptable)
    _in_memory_counters[key] = _in_memory_counters.get(key, 0) + 1
    return _in_memory_counters[key]


def counter_get(key: str) -> int:
    """Get current value of a Redis counter. Returns 0 if absent."""
    client = _get_redis()
    if client is not None:
        try:
            val = client.get(key)
            return int(val) if val is not None else 0
        except Exception as exc:
            logger.warning("redis.counter_get_failed", extra={"key": key, "error": str(exc)})
    return _in_memory_counters.get(key, 0)


# ── Rate limiting ────────────────────────────────────────────────────────────


def rate_limit_check(user_key: str, path: str, max_requests: int, window: int) -> bool:
    """Sliding window rate limiter. Returns True if allowed, False if limited.

    Uses Redis sorted sets when available, falls back to in-memory.
    """
    bucket_key = f"rl:{user_key}:{path.split('?')[0]}"
    now = time.time()

    r = _get_redis()
    if r:
        try:
            pipe = r.pipeline()
            pipe.zremrangebyscore(bucket_key, 0, now - window)
            pipe.zcard(bucket_key)
            pipe.zadd(bucket_key, {str(now): now})
            pipe.expire(bucket_key, window)
            results = pipe.execute()
            current_count = results[1]
            if current_count >= max_requests:
                # Remove the entry we just added since we're denying
                r.zrem(bucket_key, str(now))
                return False
            return True
        except Exception:
            pass

    # Fallback: in-memory (same behaviour as before but using this module)
    return _in_memory_rate_check(bucket_key, max_requests, window, now)


_rate_buckets: dict[str, list[float]] = {}


def _in_memory_rate_check(key: str, max_requests: int, window: int, now: float) -> bool:
    cutoff = now - window
    bucket = _rate_buckets.get(key, [])
    bucket = [t for t in bucket if t > cutoff]
    if len(bucket) >= max_requests:
        _rate_buckets[key] = bucket
        return False
    bucket.append(now)
    _rate_buckets[key] = bucket
    return True

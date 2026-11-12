"""Fixed-window rate limiting in Redis. Fails open (logs) if Redis is unavailable, so an outage of the cache does
not take sign-in down; the API stays protected by the reverse proxy limits in production (Phase 6)."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from fastapi import Request
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import Settings
from app.core.errors import AppError
from app.core.logging import get_logger

log = get_logger(__name__)


class RateLimiter:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def hit(self, key: str, limit: int, window_s: int) -> tuple[bool, int]:
        """Count one request; return (allowed, retry_after_seconds)."""
        now = int(time.time())
        bucket = f"rl:{key}:{now // window_s}"
        try:
            async with self.redis.pipeline(transaction=True) as pipe:
                pipe.incr(bucket)
                pipe.expire(bucket, window_s + 1)
                count, _ = await pipe.execute()
        except RedisError:
            log.warning("rate_limit_unavailable", key=key.split(":")[0])
            return True, 0
        if int(count) > limit:
            return False, window_s - now % window_s
        return True, 0


def client_ip(request: Request, settings: Settings) -> str:
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def enforce(request: Request, scope: str, identity: str, spec: str) -> None:
    settings: Settings = request.app.state.settings
    if not settings.rate_limit_enabled:
        return
    limit, window = Settings.parse_limit(spec)
    allowed, retry = await request.app.state.rate_limiter.hit(f"{scope}:{identity}", limit, window)
    if not allowed:
        raise AppError(429, "rate_limited", "Too many requests, slow down", headers={"Retry-After": str(retry)})


def limit_by_ip(scope: str, setting: str) -> Callable[[Request], Awaitable[None]]:
    """Dependency factory: limit by client IP using the ``Settings`` field named ``setting``."""

    async def dependency(request: Request) -> None:
        settings: Settings = request.app.state.settings
        await enforce(request, scope, client_ip(request, settings), getattr(settings, setting))

    return dependency

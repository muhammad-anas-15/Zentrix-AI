"""Redis caching for signals and track-record responses. Failures are logged and ignored (cache only)."""

from __future__ import annotations

import json
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.signals import Signal
from app.services.signals.serialize import signal_to_dict
from ml.data.candles import interval_seconds

log = get_logger(__name__)
TRACK_RECORD_VERSION = "trackrecord:version"


def latest_key(listing_id: int, timeframe: str, horizon: int) -> str:
    return f"signal:latest:{listing_id}:{timeframe}:{horizon}"


async def cache_latest_signals(db: AsyncSession, redis: Redis, signal_ids: list[int]) -> None:
    rows = (await db.scalars(select(Signal).where(Signal.id.in_(signal_ids)))).unique().all()
    try:
        for s in rows:
            await redis.set(latest_key(s.listing_id, s.timeframe, s.horizon), json.dumps(signal_to_dict(s)),
                            ex=2 * interval_seconds(s.timeframe))
    except Exception:
        log.debug("cache_write_failed")


async def get_cached(redis: Redis, key: str) -> Any | None:
    try:
        raw = await redis.get(key)
    except Exception:
        return None
    return json.loads(raw) if raw else None


async def set_cached(redis: Redis, key: str, value: Any, ttl_s: int) -> None:
    try:
        await redis.set(key, json.dumps(value, default=str), ex=ttl_s)
    except Exception:
        log.debug("cache_write_failed")


async def track_record_version(redis: Redis) -> int:
    try:
        return int(await redis.get(TRACK_RECORD_VERSION) or 0)
    except Exception:
        return -1  # cache bypass


async def bump_track_record_version(redis: Redis) -> None:
    """New signals or outcomes invalidate every cached track-record response."""
    try:
        await redis.incr(TRACK_RECORD_VERSION)
    except Exception:
        log.debug("cache_bump_failed")

"""Live public events over Redis pub/sub -> WebSocket clients (``/v1/stream``).

The worker publishes ``candle`` (a candle closed) and ``signal`` (a signal was created) events on one channel;
each WebSocket connection subscribes and forwards the events matching the client's subscription. Publishing is
best effort: if Redis is down, clients fall back to REST polling.
"""

from __future__ import annotations

import json
from typing import Any

from redis.asyncio import Redis

from app.core.logging import get_logger

log = get_logger(__name__)
CHANNEL = "zx:events"


async def publish(redis: Redis, event: dict[str, Any]) -> None:
    try:
        await redis.publish(CHANNEL, json.dumps(event, default=str))
    except Exception:
        log.debug("publish_failed", type=event.get("type"))


def candle_event(symbol: str, venue: str, timeframe: str, row: Any) -> dict[str, Any]:
    from app.services.marketdata.candles import ts_to_dt

    return {"type": "candle", "symbol": symbol, "venue": venue, "timeframe": timeframe,
            "candle": {"t": ts_to_dt(int(row.time)).isoformat(), "o": float(row.open), "h": float(row.high),
                       "l": float(row.low), "c": float(row.close),
                       "v": None if row.volume != row.volume else float(row.volume)}}


def matches(event: dict[str, Any], symbols: set[str], timeframes: set[str], types: set[str]) -> bool:
    return (event.get("type") in types and event.get("symbol") in symbols
            and (not timeframes or event.get("timeframe") in timeframes))

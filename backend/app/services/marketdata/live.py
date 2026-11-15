"""Live (still forming) candles for charts.

Only exchange listings with a public real-time feed are live: Binance spot and USD-M futures. The forming kline is
fetched from Binance on demand, cached for ``live_candle_cache_s`` per series with one fetch in flight (every
viewer of a chart shares it), so the load on Binance is bounded by the number of open series, not of users.
Twelve Data (FX, metals) is not live on the free plan: those charts update when each candle closes.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.core.logging import get_logger
from ml.data.sources import binance

log = get_logger(__name__)

LIVE_VENUES: dict[str, binance.Market] = {"binance_spot": "spot", "binance_usdm": "usdm"}
LIVE_TIMEFRAMES = frozenset({"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "1d", "1w"})
WEEK_S = 7 * 86400
MONDAY_OFFSET_S = 4 * 86400  # 1970-01-01 was a Thursday; exchange weeks open on Monday 00:00 UTC

Kline = dict[str, float]
Fetcher = Callable[[binance.Market, str, str, int], Awaitable[list[Kline]]]


def period_open(ts: float, tf_s: int) -> int:
    """Open time of the candle period containing ``ts`` (weeks open on Monday, like the exchanges)."""
    if tf_s == WEEK_S:
        return int((ts - MONDAY_OFFSET_S) // tf_s * tf_s + MONDAY_OFFSET_S)
    return int(ts // tf_s * tf_s)


def is_live_venue(venue: str, timeframe: str) -> bool:
    return venue in LIVE_VENUES and timeframe in LIVE_TIMEFRAMES


class LiveCandles:
    """Per-process cache of the newest klines per (venue, venue symbol, timeframe)."""

    def __init__(self, ttl_s: float, clock: Callable[[], float], fetcher: Fetcher | None = None,
                 error_ttl_s: float = 5.0, timeout_s: float = 5.0) -> None:
        self.ttl_s = ttl_s
        self.error_ttl_s = error_ttl_s
        self.clock = clock
        self.timeout_s = timeout_s
        self._fetch = fetcher or self._binance
        self._client: httpx.AsyncClient | None = None
        self._entries: dict[tuple[str, str, str], tuple[float, list[Kline] | None]] = {}
        self._locks: dict[tuple[str, str, str], asyncio.Lock] = {}
        self.fetches = 0

    async def _binance(self, market: binance.Market, venue_symbol: str, timeframe: str, limit: int) -> list[Kline]:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout_s, headers={"User-Agent": "zentrix-live/1.0"})
        r = await self._client.get(binance.BASE_URLS[market],
                                   params={"symbol": venue_symbol.upper(), "interval": timeframe, "limit": limit})
        r.raise_for_status()
        rows: list[list[Any]] = r.json()
        return [{"time": int(row[0]) // 1000, "open": float(row[1]), "high": float(row[2]), "low": float(row[3]),
                 "close": float(row[4]), "volume": float(row[5])} for row in rows]

    async def get(self, venue: str, venue_symbol: str, timeframe: str) -> list[Kline] | None:
        """The newest two klines (the last one usually still forming), oldest first; None if not live or the
        exchange is unreachable (callers fall back to stored candles)."""
        if not is_live_venue(venue, timeframe):
            return None
        key = (venue, venue_symbol, timeframe)
        async with self._locks.setdefault(key, asyncio.Lock()):
            now = self.clock()
            hit = self._entries.get(key)
            if hit is not None and hit[0] > now:
                return hit[1]
            self.fetches += 1
            try:
                rows: list[Kline] | None = await self._fetch(LIVE_VENUES[venue], venue_symbol, timeframe, 2)
                self._entries[key] = (now + self.ttl_s, rows)
            except Exception as exc:  # unreachable, blocked region, rate limited: retry after a short pause
                log.warning("live_candle_failed", venue=venue, symbol=venue_symbol, tf=timeframe,
                            error=type(exc).__name__)
                rows = None
                self._entries[key] = (now + self.error_ttl_s, None)
            return rows

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

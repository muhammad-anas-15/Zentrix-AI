"""Market-data providers keyed by venue code (``venues.code``). Async wrappers over the ML fetchers, so training
and live ingestion parse candles identically. Each returns raw candles (the newest may still be forming)."""

from __future__ import annotations

import asyncio
from typing import Protocol

import pandas as pd

from ml.data.sources import binance, twelvedata


class Provider(Protocol):
    venue: str
    timeframes: frozenset[str]

    async def fetch_latest(self, venue_symbol: str, timeframe: str, limit: int) -> pd.DataFrame: ...


class BinanceProvider:
    timeframes = frozenset({"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "1d", "1w"})

    def __init__(self, market: binance.Market) -> None:
        self.market = market
        self.venue = f"binance_{market}"

    async def fetch_latest(self, venue_symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        return await asyncio.to_thread(binance.fetch_latest, venue_symbol, timeframe, limit, None, self.market)


class TwelveDataProvider:
    venue = "twelvedata"
    timeframes = frozenset(twelvedata.TD_INTERVALS)

    async def fetch_latest(self, venue_symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        # The module throttles to the plan's per-minute limit; the worker calls it sequentially.
        return await asyncio.to_thread(twelvedata.fetch_latest, venue_symbol, timeframe, limit)


def default_providers() -> dict[str, Provider]:
    providers: list[Provider] = [BinanceProvider("usdm"), BinanceProvider("spot"), TwelveDataProvider()]
    return {p.venue: p for p in providers}

"""Live chart candles: forming klines from the exchange (cached, single flight), stored candles elsewhere."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI

from app.services.marketdata.live import LiveCandles, period_open
from ml.data.sources.binance import Market
from tests.api.conftest import Clock, seed_candles
from tests.api.test_tools import NOW, series

TF = 900
CURRENT = int(NOW.timestamp()) // TF * TF  # 14:00, forming at NOW (14:05)


class FakeExchange:
    def __init__(self, delay: float = 0, fail: bool = False) -> None:
        self.calls: list[tuple[str, str, str, int]] = []
        self.delay = delay
        self.fail = fail
        self.price = 70_000.0

    async def __call__(self, market: Market, symbol: str, tf: str, limit: int) -> list[dict[str, float]]:
        self.calls.append((market, symbol, tf, limit))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise httpx.ConnectError("blocked")
        p = self.price
        return [{"time": CURRENT - TF, "open": p - 50, "high": p + 20, "low": p - 80, "close": p - 10, "volume": 12.5},
                {"time": CURRENT, "open": p - 10, "high": p + 5, "low": p - 30, "close": p, "volume": 3.25}]


@pytest.fixture
async def exchange(app: FastAPI, clock: Clock) -> AsyncIterator[FakeExchange]:
    fake = FakeExchange()
    original = app.state.live_candles
    app.state.live_candles = LiveCandles(app.state.settings.live_candle_cache_s, clock, fetcher=fake)
    yield fake
    app.state.live_candles = original


async def test_crypto_chart_gets_the_forming_candle(client: httpx.AsyncClient, clock: Clock,
                                                    exchange: FakeExchange) -> None:
    clock.t = NOW.timestamp()
    r = await client.get("/v1/candles/live", params={"symbol": "BTC/USDT", "timeframe": "15m"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["live"] is True and body["forming"] is True and body["source"] == "binance_spot"
    assert body["candle"]["t"] == datetime.fromtimestamp(CURRENT, tz=UTC).isoformat().replace("+00:00", "Z")
    assert body["candle"]["c"] == 70_000.0 and body["candle"]["v"] == 3.25
    assert body["closed"]["c"] == 69_990.0  # the candle that just closed, with its final values
    assert datetime.fromisoformat(body["closes_at"]) == datetime.fromtimestamp(CURRENT + TF, tz=UTC)
    assert body["poll_s"] == 2 and body["market_open"] is True and body["note"] is None
    assert exchange.calls == [("spot", "BTCUSDT", "15m", 2)]
    r = await client.get("/v1/candles/live", params={"symbol": "BTC/USDT:PERP", "timeframe": "15m"})
    assert r.json()["source"] == "binance_usdm" and exchange.calls[-1][0] == "usdm"


async def test_one_exchange_request_per_series_per_second(app: FastAPI, client: httpx.AsyncClient, clock: Clock,
                                                         exchange: FakeExchange) -> None:
    clock.t = NOW.timestamp()
    exchange.delay = 0.05
    params = {"symbol": "BTC/USDT", "timeframe": "15m"}
    rs = await asyncio.gather(*(client.get("/v1/candles/live", params=params) for _ in range(8)))
    assert all(r.status_code == 200 for r in rs) and len(exchange.calls) == 1  # single flight
    exchange.price = 70_100.0
    assert (await client.get("/v1/candles/live", params=params)).json()["candle"]["c"] == 70_000.0  # cached
    clock.t = NOW.timestamp() + app.state.settings.live_candle_cache_s + 0.1
    assert (await client.get("/v1/candles/live", params=params)).json()["candle"]["c"] == 70_100.0
    assert len(exchange.calls) == 2


async def test_unreachable_exchange_falls_back_to_stored_candles(app: FastAPI, client: httpx.AsyncClient,
                                                                 clock: Clock, exchange: FakeExchange) -> None:
    clock.t = NOW.timestamp()
    exchange.fail = True
    await seed_candles(app, "BTC/USDT", "15m", series(50, start=69_000))
    params = {"symbol": "BTC/USDT", "timeframe": "15m"}
    body = (await client.get("/v1/candles/live", params=params)).json()
    assert body["live"] is False and body["source"] == "stored" and body["poll_s"] == 10
    assert "unreachable" in body["note"] and body["candle"] is not None and body["forming"] is False
    await client.get("/v1/candles/live", params=params)
    assert len(exchange.calls) == 1  # a failure is not retried on every request


async def test_fx_chart_updates_at_each_close(app: FastAPI, client: httpx.AsyncClient, clock: Clock,
                                              exchange: FakeExchange) -> None:
    clock.t = NOW.timestamp()
    await seed_candles(app, "EUR/USD", "15m", series(50))
    body = (await client.get("/v1/candles/live", params={"symbol": "EUR/USD", "timeframe": "15m"})).json()
    assert body["live"] is False and body["source"] == "stored" and exchange.calls == []
    assert body["candle"]["t"].startswith("2026-11-04T13:45")  # the last closed candle
    assert datetime.fromisoformat(body["closes_at"]) == datetime.fromtimestamp(CURRENT + TF, tz=UTC)
    assert body["poll_s"] == 60  # 10 minutes to the close: capped at a minute
    assert "closed candles only" in body["note"]
    clock.t = (NOW + timedelta(minutes=9, seconds=58)).timestamp()  # 2 s before the close
    assert (await client.get("/v1/candles/live", params={"symbol": "EUR/USD", "timeframe": "15m"})).json()[
        "poll_s"] == 10  # comes back just after the close (+ grace)
    clock.t = datetime(2026, 11, 7, 12, tzinfo=UTC).timestamp()  # Saturday: FX closed
    body = (await client.get("/v1/candles/live", params={"symbol": "EUR/USD", "timeframe": "15m"})).json()
    assert body["market_open"] is False and body["closes_at"] is None and body["poll_s"] == 60


async def test_live_candle_validation_and_own_rate_limit(app: FastAPI, client: httpx.AsyncClient,
                                                         exchange: FakeExchange) -> None:
    r = await client.get("/v1/candles/live", params={"symbol": "BTC/USDT", "timeframe": "7m"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "unknown_timeframe"
    r = await client.get("/v1/candles/live", params={"symbol": "NOPE/XYZ"})
    assert r.status_code == 404
    settings = app.state.settings
    original = settings.rate_limit_live
    settings.rate_limit_live = "3/60"
    try:
        codes = [(await client.get("/v1/candles/live", params={"symbol": "BTC/USDT"})).status_code for _ in range(3)]
        assert codes[-1] == 429  # the two calls above count in the same bucket
        assert (await client.get("/v1/timeframes")).status_code == 200  # other public reads are unaffected
    finally:
        settings.rate_limit_live = original


def test_period_open_aligns_weeks_to_monday() -> None:
    monday = datetime(2026, 11, 2, tzinfo=UTC)
    assert period_open((monday + timedelta(days=3, hours=5)).timestamp(), 7 * 86400) == monday.timestamp()
    assert period_open(NOW.timestamp(), 900) == CURRENT

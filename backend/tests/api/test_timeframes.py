"""Every chart timeframe: targets seeded per venue, FX 4h built from 1h, deferred chart series, instruments API."""

from __future__ import annotations

import time
from typing import Any

import fakeredis
import httpx
import pandas as pd
from fastapi import FastAPI
from sqlalchemy import text

from app.core.config import Settings
from app.services.marketdata.candles import aggregate, derive_candles
from app.services.signals.registry import PredictorCache
from app.workers.ingest import TickReport, Worker
from ml.data.candles import empty_frame
from tests.api.conftest import FakeGoogle, bearer, listing_id, scalar, seed_candles, sign_in

H = 3600
T0 = 1_762_128_000  # 2025-11-03 00:00 UTC, a Monday


def hourly(n: int, start: int = T0, price: float = 1.1) -> pd.DataFrame:
    rows = []
    for i in range(n):
        o = price + i * 0.001
        rows.append({"time": start + i * H, "open": o, "high": o + 0.002, "low": o - 0.001, "close": o + 0.0005,
                     "volume": 0.0})
    return pd.DataFrame(rows)


def test_aggregate_builds_closed_periods_only() -> None:
    src = hourly(10)  # 00:00 .. 09:00 -> 4h periods 00, 04 complete, 08 still open at 10:00
    out = aggregate(src, 4 * H, now_ts=T0 + 10 * H)
    assert list(out["time"]) == [T0, T0 + 4 * H]
    first = out.iloc[0]
    assert first["open"] == src["open"][0] and first["close"] == src["close"][3]
    assert first["high"] == src["high"][:4].max() and first["low"] == src["low"][:4].min()
    # history starting mid-period: that first period is incomplete and dropped
    out = aggregate(src.iloc[2:], 4 * H, now_ts=T0 + 12 * H, drop_partial_first=True)
    assert list(out["time"]) == [T0 + 4 * H, T0 + 8 * H]
    daily = aggregate(hourly(30), 86400, now_ts=T0 + 30 * H)
    assert list(daily["time"]) == [T0]


async def test_seeded_targets_cover_every_chart_timeframe(app: FastAPI) -> None:
    async def tfs(symbol: str) -> dict[str, Any]:
        lid = await listing_id(app, symbol)
        async with app.state.engine.connect() as conn:
            rows = (await conn.execute(text(
                "SELECT timeframe, derive_from, priority FROM ingestion_targets WHERE listing_id = :l AND enabled"),
                {"l": lid})).all()
        return {tf: (d, p) for tf, d, p in rows}

    btc = await tfs("BTC/USDT")
    assert {"5m", "15m", "1h", "4h", "1d"} <= set(btc) and btc["5m"][0] is None
    eur = await tfs("EUR/USD")
    assert eur["4h"] == ("1h", 55)  # built from 1h, no API calls
    assert eur["1d"][0] is None and eur["1d"][1] >= 500  # fetched after the signal series
    assert "5m" not in eur  # does not fit the Twelve Data free plan
    assert set(await tfs("AUD/JPY")) == {"1d"}


async def test_instruments_list_their_chart_timeframes(client: httpx.AsyncClient) -> None:
    items = {i["symbol"]: i for i in (await client.get("/v1/instruments", params={"limit": 200})).json()["items"]}
    assert items["BTC/USDT"]["timeframes"] == ["5m", "15m", "1h", "4h", "1d"]
    assert items["EUR/USD"]["timeframes"] == ["15m", "1h", "4h", "1d"]
    assert items["AUD/JPY"]["timeframes"] == ["1d"]


async def test_worker_builds_fx_4h_from_stored_1h(app: FastAPI, settings: Settings,
                                                  fake_redis: fakeredis.FakeAsyncRedis) -> None:
    lid = await seed_candles(app, "EUR/USD", "1h", hourly(48))
    now = T0 + 48 * H + 60
    w = Worker(app.state.sessionmaker, fake_redis, {}, PredictorCache(settings.artifacts_dir), settings,
               clock=lambda: now)
    report = await w.tick(now)
    assert report.ingested[(lid, "4h")] == 12
    rows = await scalar(app, "SELECT count(*) FROM candles WHERE listing_id = :l AND timeframe = '4h'", l=lid)
    assert rows == 12
    first_close = await scalar(app, "SELECT close FROM candles WHERE listing_id = :l AND timeframe = '4h' "
                                    "ORDER BY ts LIMIT 1", l=lid)
    assert abs(first_close - hourly(4)["close"][3]) < 1e-12
    # a later 1h candle updates only the open period, once it closes
    await seed_candles(app, "EUR/USD", "1h", hourly(4, start=T0 + 48 * H, price=1.2))
    async with app.state.sessionmaker() as db:
        n = await derive_candles(db, lid, "1h", "4h", T0 + 52 * H, since_ts=T0 + 44 * H)
        await db.commit()
    assert n == 2  # the period at 44h is rebuilt and the one at 48h is added
    assert await scalar(app, "SELECT count(*) FROM candles WHERE listing_id = :l AND timeframe = '4h'", l=lid) == 13


async def test_price_alerts_fire_on_built_4h_candles(app: FastAPI, settings: Settings, client: httpx.AsyncClient,
                                                     google: FakeGoogle, fake_redis: fakeredis.FakeAsyncRedis) -> None:
    tokens = await sign_in(client, google)
    r = await client.post("/v1/alerts", headers=bearer(tokens), json={
        "kind": "price_cross", "symbol": "EUR/USD", "timeframe": "4h", "params": {"level": 1.2, "direction": "above"}})
    assert r.status_code == 201, r.text  # EUR/USD 4h is a (built) series now
    b = int(time.time()) // (4 * H) * (4 * H) + 4 * H  # next 4h boundary, after the alert was created
    lid = await seed_candles(app, "EUR/USD", "1h", hourly(48, start=b - 48 * H))
    now = b + 4 * H + 60
    w = Worker(app.state.sessionmaker, fake_redis, {}, PredictorCache(settings.artifacts_dir), settings,
               clock=lambda: now)
    first = await w.tick(now)
    assert first.alerts == []  # never on a first build
    await seed_candles(app, "EUR/USD", "1h", hourly(4, start=b, price=1.199))  # crosses 1.20
    async with app.state.sessionmaker() as db:
        targets = await w.load_targets(db)
    report = TickReport()
    report.ingested[(lid, "1h")] = 4
    await w._derive(targets, report)
    assert len(report.alerts) == 1


class RecordingFeed:
    venue = "twelvedata"
    timeframes = frozenset({"15m", "1h", "1d"})

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def fetch_latest(self, venue_symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        self.calls.append((venue_symbol, timeframe))
        return empty_frame()


async def test_daily_chart_series_wait_for_the_signal_series(app: FastAPI, settings: Settings,
                                                             fake_redis: fakeredis.FakeAsyncRedis) -> None:
    """At 00:00 UTC every 1d series is due with the 15m/1h ones; on an 8-calls-a-minute feed the daily fetches must
    not delay the 15m signal series."""
    feed = RecordingFeed()
    now = T0 + 7 * 86400 + 30  # Monday 00:00:30 UTC
    w = Worker(app.state.sessionmaker, fake_redis, {"twelvedata": feed}, PredictorCache(settings.artifacts_dir),
               settings, clock=lambda: now)
    await w.tick(now)
    tfs = [tf for _, tf in feed.calls]
    assert "1d" in tfs and "15m" in tfs
    assert max(i for i, tf in enumerate(tfs) if tf != "1d") < min(i for i, tf in enumerate(tfs) if tf == "1d")

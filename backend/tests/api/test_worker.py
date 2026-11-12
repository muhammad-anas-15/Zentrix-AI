"""Phase 2 acceptance: signals appear without a user request, outcomes resolve automatically, and the
accuracy endpoint matches the database. Real Postgres, a real model trained by the ML pipeline on synthetic
candles, and a fake Binance feed that reveals candles as a simulated clock advances."""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from app.core.config import Settings
from app.models.signals import ModelVersion
from app.services.signals.engine import generate_signals
from app.services.signals.registry import PredictorCache, register_artifacts
from app.workers.ingest import Target, Worker
from ml.data import history
from ml.data.candles import empty_frame
from ml.demo_trading_logger import store
from ml.settings import get_settings as ml_settings
from ml.training import pipeline
from ml.training.walk_forward import WalkForwardConfig
from tests.api.conftest import scalar
from tests.conftest import make_candles, resample

pytestmark = pytest.mark.db
T_START = 1_735_689_600  # 2025-01-01 00:00 UTC
N_TRAIN, N_TOTAL = 4000, 4800
M15 = 900
PERP = "BTC/USDT:PERP"


def open_ts(i: int) -> int:
    return T_START + i * M15


def close_ts(i: int) -> int:
    return open_ts(i) + M15


@pytest.fixture(scope="session")
def market() -> pd.DataFrame:
    return make_candles(N_TOTAL, "15m", seed=42, start=T_START, price=30000.0)


@pytest.fixture(scope="session")
def artifacts(tmp_path_factory: pytest.TempPathFactory, market: pd.DataFrame) -> Iterator[Path]:
    """Train BTCUSDT 15m h1 with the real pipeline on the first N_TRAIN candles (offline cache)."""
    root = tmp_path_factory.mktemp("ml")
    env = {"DATA_CACHE_DIR": root / "cache", "ARTIFACTS_DIR": root / "artifacts", "PREDICTIONS_DB": root / "log.db"}
    saved = {k: os.environ.get(k) for k in env}
    os.environ.update({k: str(v) for k, v in env.items()})
    ml_settings.cache_clear()
    try:
        train = market.iloc[:N_TRAIN]
        history.write_cache(train, "BTCUSDT", "15m")
        history.write_cache(resample(train, "1h"), "BTCUSDT", "1h")
        conn = store.connect()
        pipeline.run_model({"symbol": "BTCUSDT", "interval": "15m", "horizon": 1}, months=2,
                           cfg=WalkForwardConfig(n_blocks=4), offline=True, conn=conn, now=close_ts(N_TRAIN - 1))
        conn.close()
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        ml_settings.cache_clear()
    yield root / "artifacts"


class FakeBinance:
    """Serves candles opened at or before ``now`` (the newest is still forming, like the real API)."""

    venue = "binance_usdm"
    timeframes = frozenset({"15m", "1h", "4h"})

    def __init__(self, base: pd.DataFrame) -> None:
        self.series = {"15m": base, "1h": resample(base, "1h"), "4h": resample(base, "4h")}
        self.now = 0
        self.fail: set[str] = set()
        self.missing: set[int] = set()
        self.calls: list[tuple[str, str, int]] = []

    async def fetch_latest(self, venue_symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        self.calls.append((venue_symbol, timeframe, limit))
        if timeframe in self.fail:
            raise ConnectionError("feed down")
        if venue_symbol != "BTCUSDT":
            return empty_frame()
        df = self.series[timeframe]
        visible = df[(df["time"] <= self.now) & ~df["time"].isin(self.missing)]
        return visible.tail(limit).reset_index(drop=True)


@pytest.fixture
async def env(app: FastAPI, settings: Settings, fake_redis: Any, artifacts: Path,
              market: pd.DataFrame) -> tuple[Worker, FakeBinance, Settings]:
    s = settings.model_copy(update={"artifacts_dir": artifacts})
    async with app.state.sessionmaker() as db:
        results = await register_artifacts(db, s)
    assert [r.status for r in results] == ["registered_active"]
    feed = FakeBinance(market)
    return Worker(app.state.sessionmaker, fake_redis, {"binance_usdm": feed}, PredictorCache(artifacts), s), feed, s


async def tick_at(worker: Worker, feed: FakeBinance, candle_index: int, delay_s: int = 15) -> Any:
    feed.now = close_ts(candle_index) + delay_s
    return await worker.tick(feed.now)


async def signal_candles(app: FastAPI) -> list[int]:
    async with app.state.engine.connect() as conn:
        rows = (await conn.execute(text("SELECT extract(epoch FROM candle_ts)::bigint FROM signals ORDER BY 1"))).all()
    return [int(r[0]) for r in rows]


Env = tuple[Worker, "FakeBinance", Settings]


async def test_signals_appear_and_outcomes_resolve_without_requests(
        app: FastAPI, client: httpx.AsyncClient, env: Env, market: pd.DataFrame) -> None:
    worker, feed, _ = env
    i0 = N_TRAIN + 200
    first = await tick_at(worker, feed, i0)
    assert max(first.ingested.values()) == 699  # backfill of 700, minus the still-forming candle
    assert len(first.signals) == 1
    for k in range(1, 6):
        r = await tick_at(worker, feed, i0 + k)
        assert len(r.signals) == 1, r.skipped
        assert sum(r.ingested.values()) >= 1
    assert await signal_candles(app) == [open_ts(i) for i in range(i0, i0 + 6)]

    # Outcomes: open-to-open label. Signal on candle i needs candles i+1 and i+2 closed -> i0..i0+3 resolved.
    async with app.state.engine.connect() as conn:
        rows = (await conn.execute(text(
            """SELECT extract(epoch FROM s.candle_ts)::bigint, s.direction, o.outcome, o.entry_price, o.exit_price
               FROM signals s JOIN signal_outcomes o ON o.signal_id = s.id ORDER BY s.candle_ts"""))).all()
    assert [int(r[0]) for r in rows] == [open_ts(i) for i in range(i0, i0 + 4)]
    for ts, direction, outcome, entry, exit_ in rows:
        i = (int(ts) - T_START) // M15
        assert entry == market["open"].iloc[i + 1] and exit_ == market["open"].iloc[i + 2]
        moved_up = exit_ > entry
        assert outcome == ("flat" if exit_ == entry else "win" if moved_up == (direction == "up") else "loss")
    # Signals were created live: within one timeframe of the candle close.
    lag = await scalar(app, "SELECT max(extract(epoch FROM created_at - decision_at)) FROM signals")
    assert 0 <= float(lag) <= M15

    # API: history, latest (cached), track record == database.
    page = (await client.get("/v1/signals", params={"symbol": PERP})).json()
    assert len(page["items"]) == 6 and page["items"][0]["outcome"] is None
    assert page["items"][-1]["outcome"]["outcome"] in {"win", "loss", "flat"}
    assert page["items"][0]["model"]["has_demonstrated_edge"] is False  # random walk: no edge
    assert page["items"][0]["strength"] == "Very Weak - Wait"
    latest = (await client.get("/v1/signals/latest", params={"symbol": PERP, "timeframe": "15m"})).json()
    assert latest["candle_time"].startswith(pd.Timestamp(open_ts(i0 + 5), unit="s").strftime("%Y-%m-%dT%H:%M"))
    record = (await client.get("/v1/track-record", params={"symbol": PERP})).json()
    async with app.state.engine.connect() as conn:
        db = (await conn.execute(text(
            """SELECT count(*), count(*) FILTER (WHERE o.signal_id IS NULL),
                      count(*) FILTER (WHERE o.outcome = 'win'), count(*) FILTER (WHERE o.outcome = 'loss'),
                      count(*) FILTER (WHERE o.outcome = 'flat'), count(*) FILTER (WHERE o.outcome = 'void')
               FROM signals s LEFT JOIN signal_outcomes o ON o.signal_id = s.id"""))).one()
    o = record["overall"]
    assert (o["signals"], o["pending"], o["wins"], o["losses"], o["flats"], o["voids"]) == tuple(db)
    assert o["hit_rate"] == (db[2] / (db[2] + db[3]) if db[2] + db[3] else None)
    assert record["by_strength"][0]["strength"] == "Very Weak - Wait"

    # Next tick resolves another signal; the cached track record updates.
    await tick_at(worker, feed, i0 + 6)
    after = (await client.get("/v1/track-record", params={"symbol": PERP})).json()["overall"]
    assert after["signals"] == 7 and after["decided"] + after["flats"] == o["decided"] + o["flats"] + 1

    candles = (await client.get("/v1/candles", params={"symbol": PERP, "timeframe": "15m", "limit": 3})).json()
    assert [c["o"] for c in candles["candles"]] == pytest.approx(list(market["open"].iloc[i0 + 4: i0 + 7]))
    models = (await client.get("/v1/models")).json()
    assert [(m["key"], m["active"], m["has_demonstrated_edge"]) for m in models] == [("BTCUSDT_15m_h1", True, False)]
    assert models[0]["reasons"] and models[0]["backtest"]["oos_signals"] > 0


async def test_no_retroactive_signals_after_downtime(app: FastAPI, env: tuple[Worker, FakeBinance, Settings]) -> None:
    worker, feed, settings = env
    i0 = N_TRAIN + 300
    await tick_at(worker, feed, i0)
    r = await tick_at(worker, feed, i0 + 12)  # worker was down for 3 hours
    assert len(r.signals) == 1  # only the newest candle; the 11 missed candles get none
    assert await signal_candles(app) == [open_ts(i0), open_ts(i0 + 12)]
    async with app.state.sessionmaker() as db:
        listing_id, instrument_id = (await db.execute(text(
            "SELECT listing_id, instrument_id FROM signals LIMIT 1"))).one()
        late = await generate_signals(db, worker.predictors, listing_id, instrument_id, "15m", open_ts(i0 + 5),
                                      feed.now)
    assert late.created == [] and "no retroactive signals" in late.skipped[0]


async def test_gap_in_label_window_voids_the_signal(app: FastAPI, env: tuple[Worker, FakeBinance, Settings]) -> None:
    worker, feed, _ = env
    i0 = N_TRAIN + 400
    await tick_at(worker, feed, i0)
    feed.missing = {open_ts(i0 + 1)}  # the provider never delivers candle i0+1
    for k in (1, 2, 3):
        await tick_at(worker, feed, i0 + k)
    async with app.state.engine.connect() as conn:
        outcome, note = (await conn.execute(text(
            "SELECT o.outcome, o.note FROM signal_outcomes o JOIN signals s ON s.id = o.signal_id "
            "WHERE s.candle_ts = to_timestamp(:t)"), {"t": open_ts(i0)})).one()
    assert outcome == "void" and "missing candles" in note


async def test_failed_higher_timeframe_skips_dependent_signal(env: tuple[Worker, FakeBinance, Settings]) -> None:
    worker, feed, _ = env
    i0 = N_TRAIN + 199  # closes on a full hour, so the 1h series is due too
    assert close_ts(i0) % 3600 == 0
    feed.fail = {"1h"}
    r = await tick_at(worker, feed, i0)
    assert r.signals == [] and any("1h data stale" in s for s in r.skipped)
    assert any(":1h:" in e for e in r.errors)


async def test_drifted_artifact_is_not_served(app: FastAPI, env: tuple[Worker, FakeBinance, Settings]) -> None:
    worker, feed, _ = env
    async with app.state.engine.begin() as conn:
        await conn.execute(text("UPDATE model_versions SET trained_at = trained_at - interval '1 day'"))
    r = await tick_at(worker, feed, N_TRAIN + 500)
    assert r.signals == [] and any("register the new version" in s for s in r.skipped)


async def test_registration_rules(app: FastAPI, settings: Settings, artifacts: Path, tmp_path: Path) -> None:
    def variant(key: str, **changes: Any) -> None:
        src = artifacts / "BTCUSDT_15m_h1"
        shutil.copytree(src, tmp_path / key)
        meta = json.loads((src / "metadata.json").read_text()) | {"key": key, **changes}
        (tmp_path / key / "metadata.json").write_text(json.dumps(meta))

    variant("EUR_USD_15m_h1", symbol="EUR/USD", venue="twelvedata")
    variant("EUR_USD_1m_h1", symbol="EUR/USD", venue="twelvedata", interval="1m", htf_interval="15m")
    variant("NZD_USD_15m_h1", symbol="NZD/USD", venue="twelvedata")  # no Twelve Data budget allocated
    variant("NOPE_15m_h1", symbol="NOPE", venue="binance_usdm")
    async with app.state.sessionmaker() as db:
        results = {r.key: r for r in await register_artifacts(db, settings, tmp_path)}
        again = {r.key: r.status for r in await register_artifacts(db, settings, tmp_path)}
    assert results["EUR_USD_15m_h1"].status == "registered_active"
    one_min, nzd = results["EUR_USD_1m_h1"], results["NZD_USD_15m_h1"]
    assert one_min.status == "registered_inactive" and "cannot ingest 1m" in one_min.detail
    assert nzd.status == "registered_inactive" and "budget" in nzd.detail
    assert results["NOPE_15m_h1"].status == "skipped"
    assert set(again.values()) <= {"already_registered", "skipped"}
    assert await scalar(app, "SELECT count(*) FROM model_versions WHERE active") == 1


def test_due_logic_respects_market_hours_and_grace(settings: Settings) -> None:
    w = Worker(None, None, {}, PredictorCache(Path(".")), settings)  # type: ignore[arg-type]
    fx = Target(1, 1, "15m", "twelvedata", "EUR/USD", "fx_24x5", 10, 700)
    def utc(*args: int) -> int:
        return int(datetime(*args, tzinfo=UTC).timestamp())

    friday_close = utc(2026, 1, 2, 22)  # Fri 22:00 UTC = 17:00 New York (EST): FX week ends
    w._last_ts = {fx.series: friday_close - 900}  # stored the week's final candle (16:45 New York)
    assert not w.is_due(fx, utc(2026, 1, 3, 12))  # Saturday: nothing to fetch
    assert not w.is_due(fx, utc(2026, 1, 4, 22, 5))  # Sunday 17:05 NY: first candle still forming
    assert w.is_due(fx, utc(2026, 1, 4, 22, 15, 15))  # Sunday 17:15:15 NY: first candle of the week closed
    tuesday = utc(2026, 1, 6, 3)
    w._last_ts = {fx.series: tuesday - 1800}
    assert not w.is_due(fx, tuesday + 5)  # inside the grace period
    assert w.is_due(fx, tuesday + 15)
    w._last_attempt[fx.series] = tuesday + 15
    assert not w.is_due(fx, tuesday + 20)  # retry spacing


async def test_twelve_data_daily_budget(settings: Settings, fake_redis: Any) -> None:
    w = Worker(None, fake_redis, {}, PredictorCache(Path(".")),  # type: ignore[arg-type]
               settings.model_copy(update={"twelve_data_daily_budget": 2}))
    now = 1_767_657_600.0
    assert [await w._budget_ok("twelvedata", now) for _ in range(3)] == [True, True, False]
    assert await w._budget_ok("binance_usdm", now)
    assert await scalar_redis(fake_redis, "budget:twelvedata:20260106") == 3


async def scalar_redis(redis: Any, key: str) -> int:
    return int(await redis.get(key))


async def test_model_versions_have_one_active_per_series(app: FastAPI, settings: Settings, artifacts: Path,
                                                         tmp_path: Path) -> None:
    newer = tmp_path / "BTCUSDT_15m_h1"
    shutil.copytree(artifacts / "BTCUSDT_15m_h1", newer)
    async with app.state.sessionmaker() as db:
        await register_artifacts(db, settings, artifacts)
        meta = json.loads((newer / "metadata.json").read_text())
        meta["trained_at"] = "2030-01-01T00:00:00+00:00"
        (newer / "metadata.json").write_text(json.dumps(meta))
        assert [r.status for r in await register_artifacts(db, settings, tmp_path)] == ["registered_active"]
        rows = (await db.execute(text("SELECT active FROM model_versions ORDER BY trained_at"))).all()
    assert [r[0] for r in rows] == [False, True]
    assert ModelVersion.__tablename__ == "model_versions"

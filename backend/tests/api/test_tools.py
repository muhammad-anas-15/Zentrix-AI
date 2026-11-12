"""Trader tools over HTTP against Postgres: conditions, levels, scenario, position size, exit advice."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pandas as pd
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from ml.features.indicators import atr
from tests.api.conftest import Clock, FakeGoogle, bearer, listing_id, seed_candles, sign_in
from tests.test_trader_tools import walk

NOW = datetime(2026, 11, 4, 14, 5, tzinfo=UTC)  # Wednesday, London / New York overlap
LAST_OPEN = int(NOW.timestamp()) // 900 * 900 - 900


def series(n: int = 1300, start: float = 1.1, seed: int = 3) -> pd.DataFrame:
    return walk(n, start=start, seed=seed, t0=LAST_OPEN - 900 * (n - 1))


async def calendar_fresh(app: FastAPI, *events: tuple[str, str, str, datetime]) -> None:
    """A fetched calendar (optionally with events: title, currency, impact, at)."""
    rows = list(events) or [("Bank Holiday", "JPY", "holiday", NOW + timedelta(days=1))]
    async with app.state.engine.begin() as conn:
        for title, cur, impact, at in rows:
            await conn.execute(text(
                "INSERT INTO news_events (source, external_id, title, currency, impact, event_at, fetched_at) "
                "VALUES ('test', :id, :t, :c, :i, :at, :f)"),
                {"id": f"{title}|{cur}|{at.isoformat()}", "t": title, "c": cur, "i": impact, "at": at,
                 "f": NOW - timedelta(minutes=5)})


async def add_signal(app: FastAPI, symbol: str, candle_open: int, direction: str = "down") -> int:
    lid = await listing_id(app, symbol)
    async with app.state.engine.begin() as conn:
        mv = (await conn.execute(text(
            "INSERT INTO model_versions (key, listing_id, timeframe, horizon, label_mode, trained_at, usable, "
            "metrics, calibration, strength, usability, active) VALUES ('EUR_USD_15m_h1', :l, '15m', 1, "
            "'open_to_open', now(), false, '{\"accuracy\": {\"rate\": 0.51}}', '{}', '{}', '{}', true) "
            "RETURNING id"), {"l": lid})).scalar()
        at = datetime.fromtimestamp(candle_open, tz=UTC)
        return int((await conn.execute(text(
            "INSERT INTO signals (model_version_id, listing_id, instrument_id, timeframe, horizon, candle_ts, "
            "decision_at, created_at, direction, p_up_raw, p_up, confidence, strength, model_usable, features) "
            "SELECT :mv, :l, instrument_id, '15m', 1, :at, :dec, :dec, :d, 0.45, 0.46, 0.54, 'Very Weak - Wait', "
            "false, '{}' FROM instrument_listings WHERE id = :l RETURNING id"),
            {"mv": mv, "l": lid, "at": at, "dec": at + timedelta(minutes=15), "d": direction})).scalar())


async def test_conditions(app: FastAPI, client: httpx.AsyncClient, clock: Clock) -> None:
    clock.t = NOW.timestamp()
    await seed_candles(app, "EUR/USD", "15m", series(600))
    r = await client.get("/v1/conditions", params={"symbol": "EUR/USD"})
    assert r.status_code == 200, r.text
    c = r.json()
    news = next(f for f in c["factors"] if f["name"] == "news")
    assert news["value"] == "unknown" and c["light"] == "amber"  # no calendar: never green
    await calendar_fresh(app)
    c = (await client.get("/v1/conditions", params={"symbol": "EUR/USD"})).json()
    assert c["light"] == "green", c["factors"]
    assert c["sessions"] == ["London", "New York"] and c["venue"] == "twelvedata"
    assert c["volatility"]["regime"] == "normal" and "does not predict" in c["method"]

    await calendar_fresh(app, ("CPI m/m", "USD", "high", NOW + timedelta(minutes=10)))
    assert (await client.get("/v1/conditions", params={"symbol": "EUR/USD"})).json()["light"] == "red"

    r = await client.get("/v1/conditions", params={"symbol": "GBP/USD"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "no_data"
    r = await client.get("/v1/conditions", params={"symbol": "EUR/USD", "timeframe": "7m"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "unknown_timeframe"


async def test_levels_and_signal_levels(app: FastAPI, client: httpx.AsyncClient, clock: Clock) -> None:
    clock.t = NOW.timestamp()
    df = series()
    await seed_candles(app, "EUR/USD", "15m", df)
    a = float(atr(df["high"], df["low"], df["close"]).iloc[-1])
    close = float(df["close"].iloc[-1])
    lv = (await client.get("/v1/levels", params={"symbol": "EUR/USD", "side": "long"})).json()
    assert lv["entry"] == round(close, 5) and lv["stop"] == round(close - 1.5 * a, 5)
    assert [t["r"] for t in lv["targets"]] == [1.0, 2.0]
    assert lv["targets"][1]["price"] == round(close + 3 * a, 5)
    br = lv["targets"][0]["base_rate"]
    assert br["entries"] >= 1000 and br["hit_rate"] == pytest.approx(0.5, abs=0.1)
    assert br["break_even_hit_rate"] == 0.5 and "not a forecast" in lv["method"]

    short = (await client.get("/v1/levels", params=[("symbol", "EUR/USD"), ("side", "short"), ("rr", "1.5"),
                                                   ("rr", "3"), ("entry", "1.2")])).json()
    assert short["entry"] == 1.2 and short["stop"] > 1.2 and [t["r"] for t in short["targets"]] == [1.5, 3.0]
    assert (await client.get("/v1/levels", params={"symbol": "EUR/USD", "side": "long", "rr": "20"})).status_code \
        == 422
    assert (await client.get("/v1/levels", params={"symbol": "EUR/USD", "side": "up"})).status_code == 422

    sid = await add_signal(app, "EUR/USD", LAST_OPEN - 900 * 100)  # a signal 100 candles ago
    sl = (await client.get(f"/v1/signals/{sid}/levels")).json()
    assert sl["side"] == "short" and sl["signal_id"] == sid
    then = df[df["time"] <= LAST_OPEN - 900 * 100]
    assert sl["entry"] == round(float(then["close"].iloc[-1]), 5)  # candles known at the signal only
    assert sl["as_of"] == datetime.fromtimestamp(LAST_OPEN - 900 * 99, tz=UTC).isoformat().replace("+00:00", "Z")
    assert any("no demonstrated edge" in n for n in sl["notes"])
    assert (await client.get("/v1/signals/999999/levels")).status_code == 404


async def test_scenario(app: FastAPI, client: httpx.AsyncClient, clock: Clock) -> None:
    clock.t = NOW.timestamp()
    await seed_candles(app, "EUR/USD", "15m", series())
    sc = (await client.get("/v1/scenario", params={"symbol": "EUR/USD", "steps": 3})).json()
    assert [s["k"] for s in sc["steps"]] == [1, 2, 3] and sc["premium"] is True
    assert all(s["coverage_tested"] == 250 and 0.6 < s["coverage"] < 0.95 for s in sc["steps"])
    assert sc["steps"][0]["low"] < sc["last_close"] < sc["steps"][0]["high"]
    assert sc["direction"] == []

    sid = await add_signal(app, "EUR/USD", LAST_OPEN)
    d = (await client.get("/v1/scenario", params={"symbol": "EUR/USD"})).json()["direction"]
    assert len(d) == 1 and d[0]["signal_id"] == sid and d[0]["p_up"] == 0.46
    assert d[0]["reliable"] is False and d[0]["has_demonstrated_edge"] is False
    assert d[0]["live_track_record"]["signals"] == 1 and d[0]["backtest_accuracy"] == 0.51
    r = await client.get("/v1/scenario", params={"symbol": "GBP/USD"})
    assert r.status_code == 404


async def size(client: httpx.AsyncClient, headers: dict[str, str] | None = None, **body: Any) -> httpx.Response:
    return await client.post("/v1/risk/position-size", json=body, headers=headers or {})


async def test_position_size(app: FastAPI, client: httpx.AsyncClient, google: FakeGoogle, clock: Clock) -> None:
    clock.t = NOW.timestamp()
    await seed_candles(app, "EUR/USD", "15m", series(100))
    await seed_candles(app, "USD/JPY", "15m", series(100, start=150.0))
    r = (await size(client, symbol="EUR/USD", entry=1.1, stop=1.095, take_profit=1.11, balance=10000)).json()
    assert r["lots"] == 0.2 and r["risk_amount"] == pytest.approx(100) and r["risk_reward"] == pytest.approx(2)
    assert r["conversion_rate"] == 1.0 and r["stop_atr"] is not None and "Not financial advice" in r["disclaimer"]

    jpy = (await size(client, symbol="USD/JPY", entry=150, stop=149.5, balance=10000)).json()
    usdjpy = (await client.get("/v1/candles", params={"symbol": "USD/JPY", "timeframe": "15m", "limit": 1})).json()
    assert jpy["conversion_rate"] == pytest.approx(1 / usdjpy["candles"][-1]["c"])
    assert "1 / USD/JPY" in jpy["conversion_notes"][0]
    assert jpy["pip_value_per_lot"] == pytest.approx(1000 * jpy["conversion_rate"])

    r = await size(client, symbol="EUR/GBP", entry=0.85, stop=0.845, balance=10000)
    assert r.status_code == 422 and r.json()["error"]["code"] == "conversion_unavailable"
    r = await size(client, symbol="EUR/GBP", entry=0.85, stop=0.845, balance=10000, conversion_rate=1.25)
    assert r.status_code == 200 and r.json()["conversion_notes"] == ["conversion rate supplied by the client"]
    btc = (await size(client, symbol="BTC/USDT", entry=60000, stop=59000, risk_amount=100, size_step=0.001)).json()
    assert btc["units"] == pytest.approx(0.1) and "USDT treated as 1 USD" in btc["conversion_notes"]

    r = await size(client, symbol="EUR/USD", entry=1.1, stop=1.1, balance=1000)
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_risk_input"
    r = await size(client, {"Authorization": "Bearer nope"}, symbol="EUR/USD", entry=1.1, stop=1.09, balance=1)
    assert r.status_code == 401  # a bad token is an error, not silently anonymous

    tokens = await sign_in(client, google)
    h = bearer(tokens)
    assert (await client.put("/v1/me/risk-profile", headers=h, json={
        "account_currency": "USD", "balance": 5000, "risk_per_trade_pct": 2, "max_daily_loss_pct": 3})).status_code \
        == 200
    mine = (await size(client, h, symbol="EUR/USD", entry=1.1, stop=1.095)).json()
    assert mine["risk_amount"] == pytest.approx(100) and mine["daily_loss_left"] == pytest.approx(150)
    clock.t = NOW.timestamp()
    r = await client.post("/v1/journal", headers=h, json={
        "symbol": "EUR/USD", "side": "long", "quantity": 12000, "entry_price": 1.1, "stop_loss": 1.09,
        "entry_at": (NOW - timedelta(hours=1)).isoformat(), "exit_price": 1.09,
        "exit_at": (NOW - timedelta(minutes=30)).isoformat()})
    assert r.status_code == 201, r.text
    after = (await size(client, h, symbol="EUR/USD", entry=1.1, stop=1.095)).json()
    assert after["daily_loss_left"] == pytest.approx(30)
    assert any("only 30.00 is left" in w for w in after["warnings"])


async def test_exit_advice(app: FastAPI, client: httpx.AsyncClient, clock: Clock) -> None:
    clock.t = NOW.timestamp()
    df = series(300)
    await seed_candles(app, "EUR/USD", "15m", df)
    await calendar_fresh(app)
    close = float(df["close"].iloc[-1])
    body = {"symbol": "EUR/USD", "side": "long", "entry_price": round(close, 5),
            "stop_loss": round(close - 0.005, 5), "take_profit": round(close + 0.02, 5),
            "opened_at": datetime.fromtimestamp(LAST_OPEN, tz=UTC).isoformat()}
    r = await client.post("/v1/exit-advice", json=body)
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["action"] in {"hold", "tighten_stop", "take_partial", "consider_exit"} and a["reasons"]
    assert a["news_state"] == "clear" and a["r_multiple"] == pytest.approx(0, abs=0.01)
    hit = (await client.post("/v1/exit-advice", json=body | {"stop_loss": round(close - 1e-5, 5),
                                                               "opened_at": None})).json()
    assert hit["action"] in {"consider_exit", "hold"}
    bad = await client.post("/v1/exit-advice", json=body | {"stop_loss": close + 0.01})
    assert bad.status_code == 422

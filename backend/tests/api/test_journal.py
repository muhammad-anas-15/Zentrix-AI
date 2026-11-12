"""Journal CRUD and P&L, statistics, rule-based review, risk profile and daily risk status."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from tests.api.conftest import Clock, FakeGoogle, bearer, seed_candles, sign_in
from tests.api.test_tools import calendar_fresh, series

NOW = datetime(2026, 11, 4, 14, 5, tzinfo=UTC)


def iso(dt: datetime) -> str:
    return dt.isoformat()


async def trade(client: httpx.AsyncClient, h: dict[str, str], minutes_ago: float, exit_after: float | None,
                result_pips: float = 0, side: str = "long", stop: bool = True, **extra: Any) -> dict[str, Any]:
    entry = 1.1
    s = 1 if side == "long" else -1
    body: dict[str, Any] = {"symbol": "EUR/USD", "side": side, "quantity": 10000, "entry_price": entry,
                            "entry_at": iso(NOW - timedelta(minutes=minutes_ago))}
    if stop:
        body["stop_loss"] = round(entry - s * 0.001, 5)  # 10 pips
    if exit_after is not None:
        body["exit_price"] = round(entry + s * result_pips * 0.0001, 5)
        body["exit_at"] = iso(NOW - timedelta(minutes=minutes_ago - exit_after))
    r = await client.post("/v1/journal", headers=h, json=body | extra)
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


async def test_journal_crud_and_pnl(app: FastAPI, client: httpx.AsyncClient, google: FakeGoogle,
                                    clock: Clock) -> None:
    clock.t = NOW.timestamp()
    h = bearer(await sign_in(client, google))
    e = await trade(client, h, 60, None, tags=["Breakout", "london", "breakout"], setup="range break")
    assert e["status"] == "open" and e["pnl_account"] is None and e["tags"] == ["breakout", "london"]
    assert e["risk_account"] == pytest.approx(10.0) and e["account_currency"] == "USD"

    r = await client.patch(f"/v1/journal/{e['id']}", headers=h,
                           json={"exit_price": 1.102, "exit_at": iso(NOW - timedelta(minutes=10)), "fees": 1.5})
    c = r.json()
    assert c["status"] == "closed" and c["pnl_quote"] == pytest.approx(20.0)
    assert c["pnl_account"] == pytest.approx(18.5) and c["r_multiple"] == pytest.approx(2.0)

    short = await trade(client, h, 30, 20, result_pips=5, side="short")
    assert short["pnl_quote"] == pytest.approx(5.0) and short["exit_price"] == pytest.approx(1.0995)

    # USD/JPY: P&L in JPY converted at the stored USD/JPY price at exit
    await seed_candles(app, "USD/JPY", "15m", series(100, start=150.0))
    jpy = (await client.post("/v1/journal", headers=h, json={
        "symbol": "USD/JPY", "side": "long", "quantity": 10000, "entry_price": 150.0, "stop_loss": 149.5,
        "entry_at": iso(NOW - timedelta(minutes=90)), "exit_price": 151.0,
        "exit_at": iso(NOW - timedelta(minutes=5))})).json()
    assert jpy["pnl_quote"] == pytest.approx(10000.0)
    assert jpy["fx_rate"] is not None and jpy["pnl_account"] == pytest.approx(10000 * jpy["fx_rate"])
    eurgbp = (await client.post("/v1/journal", headers=h, json={
        "symbol": "EUR/GBP", "side": "long", "quantity": 1000, "entry_price": 0.85,
        "entry_at": iso(NOW - timedelta(minutes=50)), "exit_price": 0.86,
        "exit_at": iso(NOW - timedelta(minutes=40))})).json()
    assert eurgbp["pnl_account"] is None and "pass conversion_rate" in eurgbp["calc_notes"][0]

    page = (await client.get("/v1/journal", headers=h, params={"status": "closed", "limit": 2})).json()
    assert len(page["items"]) == 2 and page["next_before_id"] is not None
    rest = (await client.get("/v1/journal", headers=h, params={"status": "closed",
                                                               "before_id": page["next_before_id"]})).json()
    assert len(page["items"]) + len(rest["items"]) == 4
    only = (await client.get("/v1/journal", headers=h, params={"symbol": "USD/JPY"})).json()
    assert [i["symbol"] for i in only["items"]] == ["USD/JPY"]

    other = bearer(await sign_in(client, google, sub="someone-else", email="b@example.com"))
    assert (await client.get(f"/v1/journal/{e['id']}", headers=other)).status_code == 404
    assert (await client.delete(f"/v1/journal/{e['id']}", headers=other)).status_code == 404
    assert (await client.delete(f"/v1/journal/{e['id']}", headers=h)).status_code == 204
    assert (await client.get(f"/v1/journal/{e['id']}", headers=h)).status_code == 404
    assert (await client.get("/v1/journal", headers={})).status_code == 401


@pytest.mark.parametrize("patch", [
    {"exit_price": 1.11},  # without exit_at
    {"entry_at": "2026-11-04T16:00:00+00:00"},  # future
    {"exit_price": 1.11, "exit_at": "2026-11-04T12:00:00+00:00"},  # before entry
    {"stop_loss": 1.2},  # wrong side for a long
    {"side": None},
    {"signal_id": 999999},
])
async def test_journal_validation(client: httpx.AsyncClient, google: FakeGoogle, clock: Clock,
                                  patch: dict[str, Any]) -> None:
    clock.t = NOW.timestamp()
    h = bearer(await sign_in(client, google))
    e = await trade(client, h, 60, None)
    r = await client.patch(f"/v1/journal/{e['id']}", headers=h, json=patch)
    assert r.status_code == 422, (patch, r.text)


async def test_stats_and_review(app: FastAPI, client: httpx.AsyncClient, google: FakeGoogle, clock: Clock) -> None:
    clock.t = NOW.timestamp()
    h = bearer(await sign_in(client, google))
    await calendar_fresh(app, ("CPI m/m", "USD", "high", NOW - timedelta(minutes=290)))
    # winners: short holds (10 min) and small; losers: long holds (60 min); one without stop; one inside news
    await trade(client, h, 600, 10, result_pips=5)
    await trade(client, h, 500, 10, result_pips=6)
    await trade(client, h, 400, 60, result_pips=-10)
    await trade(client, h, 335, 5, result_pips=4)  # re-entry 5 min after the loss closed
    await trade(client, h, 300, 60, result_pips=-10, stop=False)  # opened 10 min before CPI
    await trade(client, h, 200, 60, result_pips=-10, stop=False)
    await trade(client, h, 100, 10, result_pips=8, stop=False)
    await trade(client, h, 20, None)  # still open

    st = (await client.get("/v1/journal/stats", headers=h)).json()
    assert (st["trades"], st["open"], st["closed"], st["wins"], st["losses"]) == (8, 1, 7, 4, 3)
    assert st["net_pnl"] == pytest.approx(5 + 6 - 10 + 4 - 10 - 10 + 8)
    assert st["win_rate"] == pytest.approx(4 / 7) and st["profit_factor"] == pytest.approx(23 / 30)
    assert st["max_consecutive_losses"] == 2 and st["avg_r"] is not None

    rv = (await client.get("/v1/journal/review", headers=h)).json()
    codes = {i["code"] for i in rv["insights"]}
    assert {"losers_held_longer", "missing_stops", "small_winners", "news_blackout_trades",
            "quick_reentry_after_loss"} <= codes, rv
    assert rv["trades_reviewed"] == 7 and "Not financial advice" in rv["note"]

    fresh = bearer(await sign_in(client, google, sub="new-user", email="n@example.com"))
    assert (await client.get("/v1/journal/review", headers=fresh)).json()["insights"] == []


async def test_risk_profile_and_status(client: httpx.AsyncClient, google: FakeGoogle, clock: Clock) -> None:
    clock.t = NOW.timestamp()
    h = bearer(await sign_in(client, google))
    p = (await client.get("/v1/me/risk-profile", headers=h)).json()
    assert p["is_default"] is True and p["risk_per_trade_pct"] == 1.0
    st = (await client.get("/v1/me/risk-status", headers=h)).json()
    assert st["level"] == "ok" and st["daily_loss_limit"] is None and st["profile_is_default"] is True

    r = await client.put("/v1/me/risk-profile", headers=h, json={
        "account_currency": "USD", "balance": 1000, "risk_per_trade_pct": 1, "max_daily_loss_pct": 2,
        "max_trades_per_day": 3, "max_consecutive_losses": 2})
    assert r.status_code == 200 and r.json()["is_default"] is False
    assert (await client.put("/v1/me/risk-profile", headers=h, json={"risk_per_trade_pct": 0})).status_code == 422

    await trade(client, h, 120, 30, result_pips=-10)  # -10 USD
    st = (await client.get("/v1/me/risk-status", headers=h)).json()
    assert st["level"] == "ok" and st["daily_loss_used"] == pytest.approx(10)
    assert st["daily_loss_left"] == pytest.approx(10)

    await trade(client, h, 60, 50, result_pips=-9)  # closed 10 min ago: streak 2, quick re-entry window
    await trade(client, h, 5, None)  # open, 10 USD at risk
    st = (await client.get("/v1/me/risk-status", headers=h)).json()
    codes = {w["code"] for w in st["warnings"]}
    assert st["level"] == "warning", st
    assert {"daily_loss_limit_near", "open_risk_exceeds_limit", "overtrading", "loss_streak", "recent_loss"} \
        <= codes
    assert st["trades_today"] == 3 and st["consecutive_losses"] == 2 and st["open_risk"] == pytest.approx(10)

    await trade(client, h, 3, 1, result_pips=-2)
    st = (await client.get("/v1/me/risk-status", headers=h)).json()
    assert st["level"] == "stop" and "daily_loss_limit_reached" in {w["code"] for w in st["warnings"]}

    # "today" follows the user's timezone: at 01:00 Karachi time (20:00 UTC the day before) it is a new day
    await client.patch("/v1/me", headers=h, json={"timezone": "Asia/Karachi"})
    clock.t = datetime(2026, 11, 4, 20, 30, tzinfo=UTC).timestamp()
    st = (await client.get("/v1/me/risk-status", headers=h)).json()
    assert st["timezone"] == "Asia/Karachi" and st["realized_pnl_today"] == 0 and st["trades_today"] == 0

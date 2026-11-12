"""Premium tiering (no payments): the PREMIUM_ENFORCED flag, access sources, whole and partial gates, labels,
the worker and the live stream, the admin API and CLI, and OpenAPI/docs consistency."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import fakeredis
import httpx
import jwt
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from sqlalchemy import text

from app.core.config import Settings
from app.models.tools import Alert
from app.services.alerts import evaluator
from app.services.entitlements import FEATURES, PREMIUM_FEATURES
from app.services.realtime import CHANNEL
from scripts import admin as admin_cli
from tests.api.conftest import Clock, FakeGoogle, bearer, listing_id, scalar, seed_candles, sign_in
from tests.api.test_stream import WS
from tests.api.test_tools import LAST_OPEN, NOW, series

BADGE = {"label": "Premium"}
DOCS = Path(__file__).resolve().parents[3] / "docs" / "API.md"


@pytest.fixture
def enforced(settings: Settings) -> Iterator[Settings]:
    """PREMIUM_ENFORCED=true for one test (the app shares this settings object)."""
    settings.premium_enforced = True
    yield settings
    settings.premium_enforced = False


async def sql(app: FastAPI, q: str, **params: Any) -> None:
    async with app.state.engine.begin() as conn:
        await conn.execute(text(q), params)


async def account(client: httpx.AsyncClient, google: FakeGoogle, app: FastAPI, sub: str) -> tuple[dict, str]:
    """Sign in as ``sub``; returns (auth headers, user id)."""
    tokens = await sign_in(client, google, sub=sub, email=f"{sub}@example.com", name=sub.title())
    return bearer(tokens), tokens["user"]["id"]


async def set_plan(app: FastAPI, uid: str, plan: str, expires: datetime | None = None) -> None:
    await sql(app, "UPDATE users SET plan = :p, plan_expires_at = :x WHERE id = :u", p=plan, x=expires, u=uid)


async def grant(app: FastAPI, uid: str, key: str, starts: datetime | None = None, ends: datetime | None = None) -> None:
    await sql(app, "INSERT INTO entitlements (user_id, key, source, starts_at, ends_at) "
                   "VALUES (:u, :k, 'promo', :s, :e)", u=uid, k=key, s=starts or NOW - timedelta(days=1), e=ends)


async def subscription(app: FastAPI, uid: str, status: str, expires: datetime | None) -> None:
    await sql(app, "INSERT INTO subscriptions (user_id, provider, product_id, status, started_at, expires_at) "
                   "VALUES (:u, 'manual', 'premium_monthly', :s, :a, :e)",
              u=uid, s=status, a=NOW - timedelta(days=3), e=expires)


async def add_sig(app: FastAPI, symbol: str, timeframe: str, candle_open: int, *, resolved: bool = False,
                  strength: str = "Very Weak - Wait", usable: bool = False) -> int:
    """A stored signal (one active model per series), optionally with its outcome."""
    lid = await listing_id(app, symbol)
    key = f"{symbol.replace('/', '_')}_{timeframe}_h1"
    async with app.state.engine.begin() as conn:
        mv = (await conn.execute(text("SELECT id FROM model_versions WHERE key = :k"), {"k": key})).scalar()
        if mv is None:
            mv = (await conn.execute(text(
                "INSERT INTO model_versions (key, listing_id, timeframe, horizon, label_mode, trained_at, usable, "
                "metrics, calibration, strength, usability, active) VALUES (:k, :l, :tf, 1, 'open_to_open', now(), "
                ":u, '{}', '{}', '{}', '{}', true) RETURNING id"), {"k": key, "l": lid, "tf": timeframe,
                                                                   "u": usable})).scalar()
        at = datetime.fromtimestamp(candle_open, tz=UTC)
        sid = int((await conn.execute(text(
            "INSERT INTO signals (model_version_id, listing_id, instrument_id, timeframe, horizon, candle_ts, "
            "decision_at, created_at, direction, p_up_raw, p_up, confidence, strength, model_usable, features) "
            "SELECT :mv, :l, instrument_id, :tf, 1, :at, :dec, :dec, 'up', 0.6, 0.6, 0.6, :st, :u, '{}' "
            "FROM instrument_listings WHERE id = :l RETURNING id"),
            {"mv": mv, "l": lid, "tf": timeframe, "at": at, "dec": at + timedelta(minutes=15), "st": strength,
             "u": usable})).scalar())
        if resolved:
            await conn.execute(text("INSERT INTO signal_outcomes (signal_id, outcome, resolved_at) "
                                    "VALUES (:s, 'win', :r)"), {"s": sid, "r": at + timedelta(hours=1)})
    return sid


TRADE = {"symbol": "EUR/USD", "side": "long", "quantity": 10000, "entry_price": 1.1, "stop_loss": 1.099,
         "entry_at": (NOW - timedelta(hours=2)).isoformat()}
# Whole premium endpoints: (method, path template, concrete path, request kwargs, status when allowed)
GATED: list[tuple[str, str, str, dict[str, Any], int]] = [
    ("GET", "/v1/levels", "/v1/levels", {"params": {"symbol": "EUR/USD", "side": "long"}}, 200),
    ("GET", "/v1/signals/{signal_id}/levels", "/v1/signals/999999/levels", {}, 404),
    ("POST", "/v1/exit-advice", "/v1/exit-advice", {"json": {"symbol": "EUR/USD", "side": "long",
                                                             "entry_price": 1.1}}, 200),
    ("GET", "/v1/scenario", "/v1/scenario", {"params": {"symbol": "EUR/USD", "steps": 2}}, 200),
    ("POST", "/v1/journal", "/v1/journal", {"json": TRADE}, 201),
    ("PATCH", "/v1/journal/{entry_id}", "/v1/journal/999999", {"json": {"notes": "x"}}, 404),
    ("GET", "/v1/journal/stats", "/v1/journal/stats", {}, 200),
    ("GET", "/v1/journal/review", "/v1/journal/review", {}, 200),
    ("GET", "/v1/me/risk-status", "/v1/me/risk-status", {}, 200),
]
NEEDS_ACCOUNT = {"/v1/journal", "/v1/journal/{entry_id}", "/v1/journal/stats", "/v1/journal/review",
                 "/v1/me/risk-status"}


async def call(client: httpx.AsyncClient, method: str, path: str, kw: dict[str, Any],
               h: dict[str, str] | None = None) -> httpx.Response:
    return await client.request(method, path, headers=h or {}, **kw)


async def test_flag_off_everything_is_open_and_labelled(app: FastAPI, client: httpx.AsyncClient,
                                                        google: FakeGoogle, clock: Clock) -> None:
    clock.t = NOW.timestamp()
    await seed_candles(app, "EUR/USD", "15m", series())
    h, _ = await account(client, google, app, "free")
    for method, template, path, kw, ok in GATED:
        if template not in NEEDS_ACCOUNT:  # public tools: open even without an account
            r = await call(client, method, path, kw)
            assert r.status_code == ok, (path, r.text)
        r = await call(client, method, path, kw, h)
        assert r.status_code == ok, (path, r.text)
        if ok in (200, 201):
            assert r.json()["premium"]["label"] == "Premium", path
            assert r.json()["premium"]["feature"] in PREMIUM_FEATURES

    me = (await client.get("/v1/me", headers=h)).json()
    assert me["plan"] == "free" and me["premium_access"] is True and me["premium_until"] is None
    access = (await client.get("/v1/me/access", headers=h)).json()
    assert access["enforced"] is False and access["premium_access"] is True and access["plan"] == "free"
    feats = {f["key"]: f for f in access["features"]}
    assert set(feats) == set(FEATURES)
    assert all(f["available"] for f in feats.values())
    assert feats["scenario"]["via"] == "open" and feats["watchlists"]["via"] == "free"

    plans = (await client.get("/v1/plans")).json()
    assert plans["enforced"] is False and "not available yet" in plans["note"]
    assert {p["code"]: p["purchasable"] for p in plans["plans"]} == {"free": False, "premium": False}
    tiers = {f["key"]: f["tier"] for f in plans["features"]}
    assert {k for k, t in tiers.items() if t == "premium"} == set(PREMIUM_FEATURES)
    assert plans["free_markets"] == {"symbols": ["EUR/USD", "GBP/USD", "XAU/USD"], "timeframes": ["15m"]}


async def test_flag_on_premium_endpoints_refuse_free_users(app: FastAPI, client: httpx.AsyncClient,
                                                           google: FakeGoogle, clock: Clock,
                                                           enforced: Settings) -> None:
    clock.t = NOW.timestamp()
    await seed_candles(app, "EUR/USD", "15m", series())
    free_h, _ = await account(client, google, app, "free")
    prem_h, prem = await account(client, google, app, "prem")
    await set_plan(app, prem, "premium")
    for method, _, path, kw, ok in GATED:
        r = await call(client, method, path, kw)
        assert r.status_code == 401, (path, r.text)
        r = await call(client, method, path, kw, free_h)
        assert r.status_code == 403, (path, r.text)
        err = r.json()["error"]
        assert err["code"] == "premium_required" and err["details"]["feature"] in PREMIUM_FEATURES, path
        r = await call(client, method, path, kw, prem_h)
        assert r.status_code == ok, (path, r.text)
    # free features stay free
    assert (await client.get("/v1/conditions", params={"symbol": "EUR/USD"})).status_code in (200, 404)
    assert (await client.get("/v1/track-record")).status_code == 200
    assert (await client.get("/v1/me/risk-profile", headers=free_h)).status_code == 200
    plans = (await client.get("/v1/plans")).json()
    assert plans["enforced"] is True and "Purchases are not available yet" in plans["note"]
    me = (await client.get("/v1/me", headers=free_h)).json()
    assert me["plan"] == "free" and me["premium_access"] is False


async def test_access_sources_and_expiry(app: FastAPI, client: httpx.AsyncClient, google: FakeGoogle, clock: Clock,
                                         enforced: Settings) -> None:
    clock.t = NOW.timestamp()
    h, uid = await account(client, google, app, "trader")

    async def can(feature_path: str) -> bool:
        r = await client.get(feature_path, headers=h, params={"symbol": "EUR/USD", "side": "long"})
        return r.status_code not in (401, 403)

    async def access() -> dict[str, Any]:
        return (await client.get("/v1/me/access", headers=h)).json()  # type: ignore[no-any-return]

    assert not await can("/v1/scenario")
    a = await access()
    assert a["plan"] == "free" and a["premium_access"] is False
    assert {f["key"]: f["via"] for f in a["features"]}["scenario"] is None

    # admin-set plan, with an expiry
    await set_plan(app, uid, "premium", NOW + timedelta(days=30))
    assert await can("/v1/scenario") and await can("/v1/levels")
    a = await access()
    assert (a["plan"], a["source"]) == ("premium", "plan")
    assert datetime.fromisoformat(a["premium_until"]) == NOW + timedelta(days=30)
    me = (await client.get("/v1/me", headers=h)).json()
    assert me["plan"] == "premium" and me["premium_access"] is True and me["premium_until"] is not None
    await set_plan(app, uid, "premium", NOW - timedelta(seconds=1))  # expired: no job needed
    assert not await can("/v1/scenario")
    assert (await client.get("/v1/me", headers=h)).json()["plan"] == "free"
    await set_plan(app, uid, "free")

    # a grant of everything; one not started yet; one that ended
    await grant(app, uid, "premium", starts=NOW + timedelta(days=1))
    await grant(app, uid, "premium", ends=NOW - timedelta(minutes=1))
    assert not await can("/v1/scenario")
    await grant(app, uid, "premium", ends=NOW + timedelta(days=7))
    assert await can("/v1/scenario")
    assert (await access())["source"] == "grant"
    await sql(app, "DELETE FROM entitlements")

    # a single-feature trial unlocks that feature only
    await grant(app, uid, "scenario", ends=NOW + timedelta(days=3))
    assert await can("/v1/scenario") and not await can("/v1/levels")
    feats = {f["key"]: f for f in (await access())["features"]}
    assert feats["scenario"]["via"] == "grant" and feats["scenario"]["available"] is True
    assert feats["trade_levels"]["available"] is False
    assert (await access())["plan"] == "free"
    await sql(app, "DELETE FROM entitlements")

    # subscriptions (written by billing later)
    await subscription(app, uid, "cancelled", NOW + timedelta(days=10))
    await subscription(app, uid, "active", NOW - timedelta(days=1))
    assert not await can("/v1/scenario")
    await subscription(app, uid, "grace", NOW + timedelta(days=2))
    assert await can("/v1/scenario")
    assert (await access())["source"] == "subscription"

    # with the flag off again, everything is open whatever the plan
    enforced.premium_enforced = False
    await sql(app, "DELETE FROM subscriptions")
    assert await can("/v1/scenario")
    a = await access()
    assert a["premium_access"] is True and a["plan"] == "free"


async def test_signals_withhold_live_premium_markets_but_keep_the_record_complete(
        app: FastAPI, client: httpx.AsyncClient, google: FakeGoogle, clock: Clock, enforced: Settings) -> None:
    clock.t = NOW.timestamp()
    free_live = await add_sig(app, "EUR/USD", "15m", LAST_OPEN)
    jpy_done = await add_sig(app, "USD/JPY", "15m", LAST_OPEN - 7200, resolved=True)
    jpy_live = await add_sig(app, "USD/JPY", "15m", LAST_OPEN)
    eur_1h_live = await add_sig(app, "EUR/USD", "1h", LAST_OPEN // 3600 * 3600 - 3600)
    free_h, _ = await account(client, google, app, "free")
    prem_h, prem = await account(client, google, app, "prem")
    await set_plan(app, prem, "premium")

    page = (await client.get("/v1/signals")).json()
    assert [s["id"] for s in page["items"]] == [jpy_done, free_live]
    assert page["premium_locked"] == ["all_markets"]
    labels = {s["id"]: s["premium"] for s in page["items"]}
    assert labels[free_live] is None and labels[jpy_done] == {"feature": "all_markets", **BADGE}
    page = (await client.get("/v1/signals", headers=prem_h)).json()
    assert [s["id"] for s in page["items"]] == [eur_1h_live, jpy_live, jpy_done, free_live]
    assert page["premium_locked"] == []

    assert (await client.get("/v1/signals/latest", params={"symbol": "EUR/USD", "timeframe": "15m"})).json()[
        "id"] == free_live
    r = await client.get("/v1/signals/latest", params={"symbol": "USD/JPY", "timeframe": "15m"})
    assert r.status_code == 401
    r = await client.get("/v1/signals/latest", headers=free_h, params={"symbol": "EUR/USD", "timeframe": "1h"})
    assert r.status_code == 403 and r.json()["error"]["details"]["feature"] == "all_markets"
    r = await client.get("/v1/signals/latest", headers=prem_h, params={"symbol": "USD/JPY", "timeframe": "15m"})
    assert r.status_code == 200 and r.json()["id"] == jpy_live and r.json()["premium"]["feature"] == "all_markets"

    # ATR levels of a live premium-market signal would reveal its side: a trade_levels-only grant is not enough
    trial_h, trial = await account(client, google, app, "trial")
    await grant(app, trial, "trade_levels")
    r = await client.get(f"/v1/signals/{jpy_live}/levels", headers=trial_h)
    assert r.status_code == 403 and r.json()["error"]["details"]["feature"] == "all_markets"

    # the accuracy stats are never filtered
    anon_tr = (await client.get("/v1/track-record")).json()
    assert anon_tr == (await client.get("/v1/track-record", headers=prem_h)).json()


async def test_quotes_and_position_size_partial_gates(app: FastAPI, client: httpx.AsyncClient, google: FakeGoogle,
                                                      clock: Clock, enforced: Settings) -> None:
    clock.t = NOW.timestamp()
    h, uid = await account(client, google, app, "trader")
    await set_plan(app, uid, "premium")
    wl = (await client.post("/v1/watchlists", headers=h, json={"name": "W", "symbols": ["EUR/USD", "USD/JPY"]})).json()
    done = await add_sig(app, "USD/JPY", "15m", LAST_OPEN - 7200, resolved=True)
    live = await add_sig(app, "USD/JPY", "15m", LAST_OPEN)
    q = (await client.get(f"/v1/watchlists/{wl['id']}/quotes", headers=h)).json()
    jpy = {i["symbol"]: i for i in q["items"]}["USD/JPY"]
    assert jpy["latest_signal"]["id"] == live and jpy["latest_signal"]["premium"]["feature"] == "all_markets"
    assert q["premium_locked"] == []

    put = await client.put("/v1/me/risk-profile", headers=h, json={"balance": 10000})
    assert put.status_code == 200
    size = {"symbol": "EUR/USD", "entry": 1.1, "stop": 1.099, "timeframe": None}
    r = (await client.post("/v1/risk/position-size", headers=h, json=size)).json()
    assert r["daily_loss_left"] == 300 and r["premium_locked"] == []

    await set_plan(app, uid, "free")  # downgraded
    q = (await client.get(f"/v1/watchlists/{wl['id']}/quotes", headers=h)).json()
    jpy = {i["symbol"]: i for i in q["items"]}["USD/JPY"]
    assert jpy["latest_signal"]["id"] == done and q["premium_locked"] == ["all_markets"]
    r = (await client.post("/v1/risk/position-size", headers=h, json=size)).json()
    assert r["daily_loss_left"] is None and r["premium_locked"] == ["risk_guard"] and r["units"] > 0
    r = await client.post("/v1/risk/position-size", json=size | {"balance": 10000})  # anonymous: nothing withheld
    assert r.status_code == 200, r.text
    assert r.json()["premium_locked"] == []


async def test_your_data_is_never_locked(app: FastAPI, client: httpx.AsyncClient, google: FakeGoogle, clock: Clock,
                                         enforced: Settings) -> None:
    clock.t = NOW.timestamp()
    h, uid = await account(client, google, app, "trader")
    await set_plan(app, uid, "premium")
    entry = (await client.post("/v1/journal", headers=h, json=TRADE)).json()
    alert = await client.post("/v1/alerts", headers=h, json={"kind": "signal", "symbol": "EUR/USD",
                                                             "params": {"min_strength": "Good"}})
    assert alert.status_code == 201 and alert.json()["premium"] == {"feature": "signal_alerts", **BADGE}
    aid = alert.json()["id"]
    await set_plan(app, uid, "free")  # premium ended

    page = (await client.get("/v1/journal", headers=h)).json()
    assert [e["id"] for e in page["items"]] == [entry["id"]] and page["premium"]["feature"] == "journal"
    assert (await client.get(f"/v1/journal/{entry['id']}", headers=h)).status_code == 200
    r = await client.patch(f"/v1/journal/{entry['id']}", headers=h, json={"notes": "x"})
    assert r.status_code == 403 and r.json()["error"]["details"]["feature"] == "journal"
    assert (await client.get("/v1/journal/stats", headers=h)).status_code == 403
    assert (await client.delete(f"/v1/journal/{entry['id']}", headers=h)).status_code == 204

    assert (await client.get("/v1/alerts", headers=h)).json()[0]["premium"]["feature"] == "signal_alerts"
    assert (await client.patch(f"/v1/alerts/{aid}", headers=h, json={"active": False})).status_code == 200
    r = await client.patch(f"/v1/alerts/{aid}", headers=h, json={"active": True})
    assert r.status_code == 403 and r.json()["error"]["details"]["feature"] == "signal_alerts"
    r = await client.post("/v1/alerts", headers=h, json={"kind": "signal", "symbol": "EUR/USD",
                                                         "params": {"min_strength": "Good"}})
    assert r.status_code == 403
    news = await client.post("/v1/alerts", headers=h, json={"kind": "news", "params": {"lead_minutes": 30}})
    assert news.status_code == 201 and news.json()["premium"] is None  # news alerts are free
    assert (await client.delete(f"/v1/alerts/{aid}", headers=h)).status_code == 204


async def test_worker_signal_alerts_respect_entitlements(app: FastAPI, client: httpx.AsyncClient,
                                                         google: FakeGoogle, clock: Clock) -> None:
    clock.t = NOW.timestamp()
    users = {}
    for sub in ("prem", "free", "trial"):
        users[sub] = (await account(client, google, app, sub))[1]
    await set_plan(app, users["prem"], "premium")
    await grant(app, users["trial"], "signal_alerts")
    eur = await scalar(app, "SELECT id FROM instruments WHERE symbol = 'EUR/USD'")
    jpy = await scalar(app, "SELECT id FROM instruments WHERE symbol = 'USD/JPY'")
    owner = {}
    async with app.state.sessionmaker() as db:
        for sub, uid in users.items():
            for inst in (eur, jpy):
                a = Alert(user_id=uid, kind="signal", instrument_id=inst, params={"min_strength": "Good"},
                          active=True, recurring=True, cooldown_s=0, trigger_count=0,
                          created_at=NOW - timedelta(days=1))
                db.add(a)
                await db.flush()
                owner[a.id] = (sub, "EUR" if inst == eur else "JPY")
        await db.commit()
    s_eur = await add_sig(app, "EUR/USD", "15m", LAST_OPEN, strength="Good", usable=True)
    s_jpy = await add_sig(app, "USD/JPY", "15m", LAST_OPEN, strength="Good", usable=True)
    free_markets = (["EUR/USD", "GBP/USD", "XAU/USD"], ["15m"])

    async def fired(enforce: bool) -> set[tuple[str, str]]:
        await sql(app, "DELETE FROM alert_events")
        await sql(app, "UPDATE alerts SET last_triggered_at = NULL")
        async with app.state.sessionmaker() as db:
            await evaluator.on_signals(db, [s_eur, s_jpy], NOW, premium_enforced=enforce, free_markets=free_markets)
            await db.commit()
        async with app.state.engine.connect() as conn:
            rows = (await conn.execute(text("SELECT alert_id FROM alert_events"))).scalars().all()
        return {owner[r] for r in rows}

    assert await fired(True) == {("prem", "EUR"), ("prem", "JPY"), ("trial", "EUR")}
    assert await fired(False) == {(u, m) for u in users for m in ("EUR", "JPY")}


async def test_stream_signal_events_need_all_markets(app: FastAPI, client: httpx.AsyncClient, google: FakeGoogle,
                                                     clock: Clock, fake_redis: fakeredis.FakeAsyncRedis,
                                                     enforced: Settings) -> None:
    clock.t = NOW.timestamp()
    free_tokens = await sign_in(client, google, sub="free", email="free@example.com")
    prem_tokens = await sign_in(client, google, sub="prem", email="prem@example.com")
    await set_plan(app, prem_tokens["user"]["id"], "premium")

    def signal(symbol: str, sid: int) -> str:
        return json.dumps({"type": "signal", "symbol": symbol, "timeframe": "15m", "id": sid})

    ws = WS(app)
    assert (await ws.connect())["type"] == "websocket.accept"
    hello = await ws.recv()
    assert hello["premium_enforced"] is True and hello["free_markets"]["timeframes"] == ["15m"]
    await ws.send({"action": "subscribe", "symbols": ["EUR/USD", "USD/JPY"], "types": ["signal"]})
    assert (await ws.recv())["type"] == "subscribed"
    await fake_redis.publish(CHANNEL, signal("USD/JPY", 1))  # premium market: withheld
    await fake_redis.publish(CHANNEL, signal("EUR/USD", 2))
    got = await ws.recv()
    assert got["id"] == 2 and "premium" not in got

    await ws.send({"action": "auth", "access_token": free_tokens["access_token"]})
    assert await ws.recv() == {"type": "authenticated", "plan": "free", "all_markets": False,
                               "expires_at": token_expiry(free_tokens)}
    await fake_redis.publish(CHANNEL, signal("USD/JPY", 3))
    await fake_redis.publish(CHANNEL, signal("EUR/USD", 4))
    assert (await ws.recv())["id"] == 4

    await ws.send({"action": "auth", "access_token": prem_tokens["access_token"]})
    auth = await ws.recv()
    assert auth["type"] == "authenticated" and auth["plan"] == "premium" and auth["all_markets"] is True
    await fake_redis.publish(CHANNEL, signal("USD/JPY", 5))
    got = await ws.recv()
    assert got["id"] == 5 and got["premium"] == {"feature": "all_markets", **BADGE}

    clock.t = datetime.fromisoformat(auth["expires_at"]).timestamp() + 1  # the token expired: back to free
    await fake_redis.publish(CHANNEL, signal("USD/JPY", 6))
    await fake_redis.publish(CHANNEL, signal("EUR/USD", 7))
    assert (await ws.recv())["id"] == 7

    await ws.send({"action": "auth", "access_token": "not-a-token"})
    err = await ws.recv()
    assert err["type"] == "error" and err["code"] == "invalid_token"
    await ws.close()


def token_expiry(tokens: dict[str, Any]) -> str:
    exp = jwt.decode(tokens["access_token"], options={"verify_signature": False})["exp"]
    return datetime.fromtimestamp(exp, tz=UTC).isoformat()


async def test_admin_sets_plans_and_grants(app: FastAPI, client: httpx.AsyncClient, google: FakeGoogle,
                                           clock: Clock, enforced: Settings) -> None:
    clock.t = NOW.timestamp()
    admin_h, admin_id = await account(client, google, app, "boss")
    user_h, uid = await account(client, google, app, "trader")
    assert (await client.get("/v1/admin/users")).status_code == 401
    r = await client.get("/v1/admin/users", headers=admin_h)
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"  # not an admin yet
    await sql(app, "UPDATE users SET is_admin = true WHERE id = :u", u=admin_id)

    r = (await client.get("/v1/admin/users", headers=admin_h, params={"q": "TRADER"})).json()
    assert r["total"] == 1 and r["items"][0]["id"] == uid and r["items"][0]["effective_plan"] == "free"
    assert (await client.get("/v1/admin/users", headers=admin_h, params={"plan": "premium"})).json()["total"] == 0
    assert (await client.get("/v1/admin/users", headers=admin_h, params={"q": "%_"})).json()["total"] == 0
    r = await client.get("/v1/admin/users/00000000-0000-0000-0000-000000000000", headers=admin_h)
    assert r.status_code == 404
    assert (await client.get(f"/v1/admin/users/{uid}", headers=user_h)).status_code == 403

    until = NOW + timedelta(days=30)
    url = f"/v1/admin/users/{uid}/plan"
    for bad in ({"plan": "premium", "expires_at": (NOW - timedelta(days=1)).isoformat(), "reason": "late"},
                {"plan": "free", "expires_at": until.isoformat(), "reason": "nope"},
                {"plan": "premium"}, {"plan": "gold", "reason": "nope"}):
        assert (await client.put(url, headers=admin_h, json=bad)).status_code == 422, bad
    r = await client.put(url, headers=admin_h, json={"plan": "premium", "expires_at": until.isoformat(),
                                                     "reason": "beta tester", "is_admin": True})
    assert r.status_code == 200, r.text
    d = r.json()
    assert (d["plan"], d["effective_plan"], d["premium_source"], d["is_admin"]) == ("premium", "premium", "plan",
                                                                                     False)
    assert (await client.get("/v1/scenario", headers=user_h, params={"symbol": "EUR/USD"})).status_code == 404
    me = (await client.get("/v1/me", headers=user_h)).json()
    assert me["plan"] == "premium" and me["premium_access"] is True
    async with app.state.engine.connect() as conn:
        row = (await conn.execute(text("SELECT event, user_id, meta FROM audit_log WHERE event LIKE 'admin.%'"))).one()
    assert row[0] == "admin.plan_set" and str(row[1]) == uid
    assert row[2]["actor"] == admin_id and row[2]["reason"] == "beta tester"
    assert row[2]["from"] == {"plan": "free", "expires_at": None} and row[2]["to"]["plan"] == "premium"

    r = await client.put(url, headers=admin_h, json={"plan": "free", "reason": "beta ended"})
    assert r.json()["effective_plan"] == "free" and r.json()["plan_expires_at"] is None
    assert (await client.get("/v1/scenario", headers=user_h, params={"symbol": "EUR/USD"})).status_code == 403

    gurl = f"/v1/admin/users/{uid}/entitlements"
    assert (await client.post(gurl, headers=admin_h, json={"key": "gold"})).status_code == 422
    r = await client.post(gurl, headers=admin_h, json={"key": "scenario", "ends_at": (NOW - timedelta(hours=1))
                                                       .isoformat()})
    assert r.status_code == 422
    r = await client.post(gurl, headers=admin_h, json={"key": "scenario", "source": "promo", "note": "trial",
                                                       "ends_at": (NOW + timedelta(days=7)).isoformat()})
    assert r.status_code == 201, r.text
    g = r.json()
    assert g["active"] is True and g["granted_by"] == admin_id and g["source"] == "promo"
    assert (await client.get("/v1/scenario", headers=user_h, params={"symbol": "EUR/USD"})).status_code == 404
    d = (await client.get(f"/v1/admin/users/{uid}", headers=admin_h)).json()
    assert [e["key"] for e in d["entitlements"]] == ["scenario"] and d["effective_plan"] == "free"

    r = await client.delete(f"{gurl}/{g['id']}", headers=admin_h, params={"reason": "abuse"})
    assert r.status_code == 200 and r.json()["active"] is False
    assert (await client.get("/v1/scenario", headers=user_h, params={"symbol": "EUR/USD"})).status_code == 403
    assert (await client.delete(f"{gurl}/999999", headers=admin_h)).status_code == 404
    events = await scalar(app, "SELECT string_agg(event, ',' ORDER BY id) FROM audit_log WHERE event LIKE 'admin.%'")
    assert events == "admin.plan_set,admin.plan_set,admin.entitlement_granted,admin.entitlement_ended"

    # account deletion: the user's grants go, the audit trail stays (without the user id); grants survive
    # their admin's deletion with granted_by cleared
    _, other = await account(client, google, app, "other")
    await client.post(f"/v1/admin/users/{other}/entitlements", headers=admin_h, json={"key": "premium"})
    assert (await client.delete("/v1/me", headers=user_h)).status_code == 204
    assert await scalar(app, "SELECT count(*) FROM entitlements WHERE user_id = :u", u=uid) == 0
    assert await scalar(app, "SELECT count(*) FROM audit_log WHERE event LIKE 'admin.%' AND user_id IS NULL") == 4
    assert (await client.delete("/v1/me", headers=admin_h)).status_code == 204
    assert await scalar(app, "SELECT granted_by FROM entitlements WHERE user_id = :u", u=other) is None


async def test_admin_cli(app: FastAPI, client: httpx.AsyncClient, google: FakeGoogle, settings: Settings) -> None:
    _, uid = await account(client, google, app, "ops")
    assert "admin=False" in await admin_cli.run(["show", "OPS@example.com"], settings)
    assert await admin_cli.run(["make-admin", "ops@example.com"], settings) == "ops@example.com: admin=True"
    assert await scalar(app, "SELECT is_admin FROM users WHERE id = :u", u=uid) is True
    out = await admin_cli.run(["set-plan", uid, "premium", "--until", "2030-01-01", "--reason", "founder"], settings)
    assert "plan=premium" in out
    assert "effective=premium source=plan" in await admin_cli.run(["show", uid], settings)
    with pytest.raises(admin_cli.AdminError):
        await admin_cli.run(["set-plan", uid, "premium", "--until", "2020-01-01", "--reason", "x"], settings)
    with pytest.raises(admin_cli.AdminError):
        await admin_cli.run(["show", "nobody@example.com"], settings)
    await admin_cli.run(["revoke-admin", uid], settings)
    assert await scalar(app, "SELECT is_admin FROM users WHERE id = :u", u=uid) is False
    actors = await scalar(app, "SELECT string_agg(DISTINCT meta->>'actor', ',') FROM audit_log "
                               "WHERE event LIKE 'admin.%'")
    assert actors == "cli"


def api_routes(app: FastAPI) -> Iterator[tuple[str, APIRoute]]:
    """(full path, route) for every API route, whether this FastAPI flattens included routers or keeps them."""
    for r in app.routes:
        if isinstance(r, APIRoute):
            yield r.path, r
        elif hasattr(r, "original_router"):  # FastAPI >= 0.16x: an included router
            prefix = r.include_context.prefix
            yield from ((prefix + sub.path, sub) for sub in r.original_router.routes if isinstance(sub, APIRoute))


def _gate_feature(route: APIRoute) -> str | None:
    stack = list(route.dependant.dependencies)
    while stack:
        d = stack.pop()
        feature = getattr(d.call, "premium_feature", None)
        if feature:
            return str(feature)
        stack += d.dependencies
    return None


def _uses_gate(route: APIRoute) -> bool:
    stack = list(route.dependant.dependencies)
    while stack:
        d = stack.pop()
        if getattr(d.call, "__name__", "") == "get_gate":
            return True
        stack += d.dependencies
    return False


def test_openapi_marks_match_gates_and_docs(app: FastAPI) -> None:
    spec = app.openapi()
    full, partial = set(), set()
    for path, route in api_routes(app):
        for method in route.methods:
            op = spec["paths"][path][method.lower()]
            mark, gate = op.get("x-premium"), _gate_feature(route)
            if gate:
                assert mark == {"feature": gate, "scope": "full"}, path
                assert op["summary"].endswith("(Premium)"), path
                full.add((method, path))
                ok = next(c for c in ("200", "201") if c in op["responses"])
                ref = op["responses"][ok]["content"]["application/json"]["schema"]["$ref"].rsplit("/", 1)[1]
                assert spec["components"]["schemas"][ref]["properties"]["premium"], path  # the label
            elif mark is not None:
                assert mark["scope"] == "partial" and _uses_gate(route), path
                partial.add((method, path))
    assert full == {(m, t) for m, t, *_ in GATED}  # the gate test above covers every premium endpoint
    assert len(partial) == 6
    docs = DOCS.read_text(encoding="utf-8")
    for feature in PREMIUM_FEATURES:
        assert f"`{feature}`" in docs, feature

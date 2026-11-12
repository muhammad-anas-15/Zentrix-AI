"""Watchlists, devices, alerts (rules, evaluation, inbox), push delivery (FCM HTTP v1) and the worker hook-up."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import fakeredis
import httpx
import jwt
import numpy as np
import pandas as pd
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from sqlalchemy import select, text

from app.core.config import Settings
from app.models.tools import Alert
from app.services.alerts import evaluator
from app.services.alerts.push import DisabledSender, FcmSender, SendResult, deliver_pending
from app.services.realtime import CHANNEL
from app.services.signals.registry import PredictorCache
from app.workers.ingest import Worker
from ml.data.candles import empty_frame
from tests.api.conftest import Clock, FakeGoogle, bearer, listing_id, scalar, seed_candles, sign_in
from tests.api.test_tools import add_signal, calendar_fresh, series

NOW = datetime(2026, 11, 4, 14, 5, tzinfo=UTC)
LAST_OPEN = int(NOW.timestamp()) // 900 * 900 - 900


async def user(client: httpx.AsyncClient, google: FakeGoogle, sub: str = "google-sub-1") -> dict[str, str]:
    return bearer(await sign_in(client, google, sub=sub, email=f"{sub}@example.com"))


# ---- watchlists -------------------------------------------------------------------------------------------------

async def test_watchlists_crud_and_quotes(app: FastAPI, client: httpx.AsyncClient, google: FakeGoogle,
                                          clock: Clock) -> None:
    clock.t = NOW.timestamp()
    h = await user(client, google)
    r = await client.post("/v1/watchlists", headers=h, json={"name": "FX", "symbols": ["EUR/USD", "XAU/USD",
                                                                                      "EUR/USD"]})
    assert r.status_code == 201, r.text
    wl = r.json()
    assert [i["symbol"] for i in wl["items"]] == ["EUR/USD", "XAU/USD"]
    assert (await client.post("/v1/watchlists", headers=h, json={"name": "FX"})).json()["error"]["code"] \
        == "name_taken"
    bad = await client.post("/v1/watchlists", headers=h, json={"name": "X", "symbols": ["NOPE/USD"]})
    assert bad.status_code == 422 and bad.json()["error"]["details"] == ["NOPE/USD"]

    wid = wl["id"]
    r = await client.post(f"/v1/watchlists/{wid}/items", headers=h, json={"symbol": "BTC/USDT"})
    assert [i["symbol"] for i in r.json()["items"]] == ["EUR/USD", "XAU/USD", "BTC/USDT"]
    r = await client.put(f"/v1/watchlists/{wid}/items", headers=h, json={"symbols": ["BTC/USDT", "EUR/USD"]})
    assert [i["symbol"] for i in r.json()["items"]] == ["BTC/USDT", "EUR/USD"]
    r = await client.delete(f"/v1/watchlists/{wid}/items", headers=h, params={"symbol": "BTC/USDT"})
    assert [i["symbol"] for i in r.json()["items"]] == ["EUR/USD"]
    r = await client.patch(f"/v1/watchlists/{wid}", headers=h, json={"name": "Majors"})
    assert r.json()["name"] == "Majors"

    other = await user(client, google, "other")
    assert (await client.get(f"/v1/watchlists/{wid}/quotes", headers=other)).status_code == 404
    assert (await client.get("/v1/watchlists", headers=other)).json() == []

    df = series(300)
    await seed_candles(app, "EUR/USD", "15m", df)
    await calendar_fresh(app, ("CPI m/m", "USD", "high", NOW + timedelta(minutes=50)))
    sid = await add_signal(app, "EUR/USD", LAST_OPEN, "up")
    q = (await client.get(f"/v1/watchlists/{wid}/quotes", headers=h)).json()["items"][0]
    assert q["price"] == pytest.approx(float(df["close"].iloc[-1]))
    day_ago = df[df["time"] <= LAST_OPEN - 86400]["close"].iloc[-1]
    assert q["change_24h_pct"] == pytest.approx((df["close"].iloc[-1] / day_ago - 1) * 100)
    assert q["news_state"] == "caution" and q["next_event"] == "USD CPI m/m" and q["next_event_in_s"] == 3000
    assert q["latest_signal"]["id"] == sid and q["latest_signal"]["has_demonstrated_edge"] is False

    assert (await client.delete(f"/v1/watchlists/{wid}", headers=h)).status_code == 204
    assert (await client.get("/v1/watchlists", headers=h)).json() == []


# ---- devices ----------------------------------------------------------------------------------------------------

async def test_devices(client: httpx.AsyncClient, google: FakeGoogle) -> None:
    a, b = await user(client, google, "a"), await user(client, google, "b")
    token = "fcm-token-" + "x" * 30 + "abc123"
    d = (await client.post("/v1/devices", headers=a, json={"fcm_token": token, "platform": "android"})).json()
    assert d["token_hint"] == "abc123" and "fcm_token" not in d
    moved = (await client.post("/v1/devices", headers=b, json={"fcm_token": token, "platform": "android",
                                                              "app_version": "1.0.0"})).json()
    assert moved["id"] == d["id"]  # the token follows whoever signed in on that phone last
    assert (await client.get("/v1/devices", headers=a)).json() == []
    assert (await client.delete(f"/v1/devices/{d['id']}", headers=a)).status_code == 404
    assert (await client.delete(f"/v1/devices/{d['id']}", headers=b)).status_code == 204


# ---- alert rules ------------------------------------------------------------------------------------------------

async def test_alert_crud_and_validation(client: httpx.AsyncClient, google: FakeGoogle) -> None:
    h = await user(client, google)
    ok = await client.post("/v1/alerts", headers=h, json={
        "kind": "price_cross", "symbol": "EUR/USD", "params": {"level": 1.105, "direction": "above"}})
    assert ok.status_code == 201, ok.text
    a = ok.json()
    assert (a["timeframe"], a["recurring"], a["active"]) == ("15m", False, True)

    wl = (await client.post("/v1/watchlists", headers=h, json={"name": "W", "symbols": ["EUR/USD"]})).json()
    sig = (await client.post("/v1/alerts", headers=h, json={
        "kind": "signal", "watchlist_id": wl["id"], "params": {"min_strength": "Good"}})).json()
    assert sig["recurring"] is True and sig["symbol"] is None

    bad = [
        {"kind": "price_cross", "params": {"level": 1.1, "direction": "above"}},  # no symbol
        {"kind": "pct_move", "symbol": "EUR/USD", "params": {"pct": 0}},
        {"kind": "signal", "symbol": "EUR/USD", "params": {"min_strength": "Very Weak - Wait"}},
        {"kind": "signal", "symbol": "EUR/USD", "watchlist_id": wl["id"], "params": {"min_strength": "Good"}},
        {"kind": "news", "params": {"lead_minutes": 1}},
        {"kind": "telepathy", "symbol": "EUR/USD", "params": {}},
    ]
    for body in bad:
        assert (await client.post("/v1/alerts", headers=h, json=body)).status_code == 422, body
    r = await client.post("/v1/alerts", headers=h, json={
        "kind": "price_cross", "symbol": "EUR/GBP", "params": {"level": 0.86, "direction": "above"}})
    assert r.status_code == 422 and r.json()["error"]["code"] == "series_not_ingested"
    r = await client.post("/v1/alerts", headers=h, json={
        "kind": "pct_move", "symbol": "EUR/USD", "timeframe": "4h", "params": {"pct": 1}})
    assert r.json()["error"]["details"]["available_timeframes"] == ["15m", "1h"]

    upd = await client.patch(f"/v1/alerts/{a['id']}", headers=h, json={"params": {"level": 1.2, "direction":
                                                                                   "below"}, "active": False})
    assert upd.json()["params"] == {"level": 1.2, "direction": "below"} and upd.json()["active"] is False
    assert (await client.patch(f"/v1/alerts/{a['id']}", headers=h, json={"params": {"level": -1}})).status_code \
        == 422
    assert [x["id"] for x in (await client.get("/v1/alerts", headers=h, params={"active": True})).json()] \
        == [sig["id"]]
    other = await user(client, google, "other")
    assert (await client.get(f"/v1/alerts/{a['id']}", headers=other)).status_code == 404
    assert (await client.delete(f"/v1/alerts/{a['id']}", headers=h)).status_code == 204


# ---- evaluation -------------------------------------------------------------------------------------------------

def flat(n: int, price: float = 1.1, t_last: int = LAST_OPEN) -> pd.DataFrame:
    t = t_last - 900 * (n - 1) + 900 * np.arange(n)
    return pd.DataFrame({"time": t, "open": price, "high": price + 0.0002, "low": price - 0.0002,
                         "close": price, "volume": 1.0})


async def make_alert(app: FastAPI, uid: str, **kw: Any) -> int:
    async with app.state.sessionmaker() as db:
        a = Alert(**({"user_id": uid, "active": True, "trigger_count": 0, "cooldown_s": 0, "recurring": False,
                      "created_at": NOW - timedelta(days=1)} | kw))
        db.add(a)
        await db.commit()
        return int(a.id)


async def uid_of(app: FastAPI) -> str:
    return str(await scalar(app, "SELECT id FROM users ORDER BY created_at LIMIT 1"))


async def test_price_and_move_alerts_fire_once_on_recent_closed_candles(app: FastAPI, client: httpx.AsyncClient,
                                                                       google: FakeGoogle) -> None:
    await sign_in(client, google)
    uid = await uid_of(app)
    inst = await scalar(app, "SELECT id FROM instruments WHERE symbol = 'EUR/USD'")
    lid = await listing_id(app, "EUR/USD")
    df = flat(50)
    df.loc[49, ["high", "close"]] = [1.1062, 1.1055]  # last candle wicks through 1.1060
    await seed_candles(app, "EUR/USD", "15m", df)
    cross = await make_alert(app, uid, kind="price_cross", instrument_id=inst, timeframe="15m",
                             params={"level": 1.106, "direction": "above"})
    below = await make_alert(app, uid, kind="price_cross", instrument_id=inst, timeframe="15m",
                             params={"level": 1.09, "direction": "below"})
    move = await make_alert(app, uid, kind="pct_move", instrument_id=inst, timeframe="15m", recurring=True,
                            params={"pct": 0.4, "window_candles": 4, "direction": "up"})
    other_tf = await make_alert(app, uid, kind="pct_move", instrument_id=inst, timeframe="1h",
                                params={"pct": 0.1, "window_candles": 1, "direction": "either"})
    close_at = datetime.fromtimestamp(LAST_OPEN + 900 + 5, tz=UTC)
    async with app.state.sessionmaker() as db:
        fired = await evaluator.on_candles(db, inst, lid, "15m", LAST_OPEN - 900, close_at)
        await db.commit()
        again = await evaluator.on_candles(db, inst, lid, "15m", LAST_OPEN - 900, close_at)
        await db.commit()
        late = await evaluator.on_candles(db, inst, lid, "15m", LAST_OPEN - 900, close_at + timedelta(hours=3))
    assert len(fired) == 2 and again == [] and late == []
    async with app.state.engine.connect() as conn:
        rows = (await conn.execute(text("SELECT alert_id, title, body FROM alert_events ORDER BY id"))).all()
        states = dict((await conn.execute(text("SELECT id, active FROM alerts"))).all())
    assert [r[0] for r in rows] == [cross, move]
    assert rows[0][1] == "EUR/USD above 1.10600" and "Not financial advice" in rows[0][2]
    assert "+0.50% in 4 x 15m" in rows[1][1]
    assert states == {cross: False, below: True, move: True, other_tf: True}  # one-shot switched off


async def test_catch_up_never_bursts_old_candles_or_fires_before_creation(
        app: FastAPI, client: httpx.AsyncClient, google: FakeGoogle) -> None:
    """Regression (live run): after a catch-up, a new alert fired on 14 one-minute candles that had closed before
    it was created. Only the last two candles count, and only those closing after the alert was created."""
    await sign_in(client, google)
    uid = await uid_of(app)
    inst = await scalar(app, "SELECT id FROM instruments WHERE symbol = 'EUR/USD'")
    lid = await listing_id(app, "EUR/USD")
    df = flat(60)
    df.loc[50:, "close"] = [1.1 + 0.0001 * (i % 2) for i in range(10)]  # every candle moves
    await seed_candles(app, "EUR/USD", "15m", df)
    params = {"pct": 0.001, "window_candles": 1, "direction": "either"}
    old = await make_alert(app, uid, kind="pct_move", instrument_id=inst, timeframe="15m", recurring=True,
                           params=params)
    second_last_close = datetime.fromtimestamp(LAST_OPEN, tz=UTC)  # close of the second-to-last candle
    new = await make_alert(app, uid, kind="pct_move", instrument_id=inst, timeframe="15m", recurring=True,
                           params=params, created_at=second_last_close + timedelta(seconds=1))
    now = datetime.fromtimestamp(LAST_OPEN + 900 + 5, tz=UTC)
    async with app.state.sessionmaker() as db:
        fired = await evaluator.on_candles(db, inst, lid, "15m", LAST_OPEN - 900 * 10, now)  # 10 new candles
        await db.commit()
    async with app.state.engine.connect() as conn:
        rows = (await conn.execute(text("SELECT alert_id, triggered_at FROM alert_events ORDER BY id"))).all()
    assert len(fired) == 3
    assert [r[0] for r in rows] == [old, old, new]
    assert rows[-1][1] == now - timedelta(seconds=5)


async def test_signal_and_news_alerts(app: FastAPI, client: httpx.AsyncClient, google: FakeGoogle) -> None:
    h = await user(client, google)
    uid = await uid_of(app)
    wl = (await client.post("/v1/watchlists", headers=h, json={"name": "W", "symbols": ["EUR/USD"]})).json()
    jpy = (await client.post("/v1/watchlists", headers=h, json={"name": "J", "symbols": ["AUD/JPY"]})).json()
    good = await make_alert(app, uid, kind="signal", watchlist_id=wl["id"], recurring=True,
                            params={"min_strength": "Good"})
    strong = await make_alert(app, uid, kind="signal", watchlist_id=wl["id"], recurring=True,
                              params={"min_strength": "Strong"})
    sid = await add_signal(app, "EUR/USD", LAST_OPEN)  # 'Very Weak - Wait', no edge: never alerts
    async with app.state.sessionmaker() as db:
        assert await evaluator.on_signals(db, [sid], NOW) == []
    async with app.state.engine.begin() as conn:
        await conn.execute(text("UPDATE signals SET strength = 'Good', model_usable = true WHERE id = :i"),
                           {"i": sid})
    async with app.state.sessionmaker() as db:
        fired = await evaluator.on_signals(db, [sid], NOW)
        await db.commit()
    assert len(fired) == 1
    ev = (await client.get("/v1/alerts/events", headers=h)).json()
    assert ev["unread"] == 1 and ev["items"][0]["alert_id"] == good and strong != good
    assert ev["items"][0]["title"] == "EUR/USD 15m: DOWN (Good)" and ev["items"][0]["delivery"] == "pending"

    await calendar_fresh(app, ("CPI m/m", "USD", "high", NOW + timedelta(minutes=20)),
                         ("Retail Sales", "AUD", "medium", NOW + timedelta(minutes=10)))
    news_all = await make_alert(app, uid, kind="news", recurring=True, params={"lead_minutes": 30,
                                                                               "min_impact": "high"})
    news_jpy = await make_alert(app, uid, kind="news", watchlist_id=jpy["id"], recurring=True,
                                params={"lead_minutes": 30, "min_impact": "medium"})
    async with app.state.sessionmaker() as db:
        fired = await evaluator.news_tick(db, NOW)
        await db.commit()
        assert await evaluator.news_tick(db, NOW + timedelta(minutes=1)) == []  # deduplicated per event
    titles = {e["title"]: e["alert_id"] for e in (await client.get("/v1/alerts/events", headers=h)).json()["items"]}
    assert titles == {"EUR/USD 15m: DOWN (Good)": good, "USD CPI m/m in 20 min": news_all,
                      "AUD Retail Sales in 10 min": news_jpy}
    assert len(fired) == 2

    r = await client.post("/v1/alerts/events/read", headers=h, json={"all": True})
    assert r.json() == {"updated": 3}
    assert (await client.get("/v1/alerts/events", headers=h, params={"unread_only": True})).json()["items"] == []


# ---- push -------------------------------------------------------------------------------------------------------

class FakeSender:
    enabled = True

    def __init__(self) -> None:
        self.results: dict[str, SendResult] = {}
        self.sent: list[tuple[str, str]] = []

    async def send(self, token: str, title: str, body: str, data: dict[str, str]) -> SendResult:
        self.sent.append((token, title))
        return self.results.get(token, SendResult(True))


async def test_push_delivery_outbox(app: FastAPI, client: httpx.AsyncClient, google: FakeGoogle) -> None:
    h = await user(client, google)
    uid = await uid_of(app)
    good, dead = "tok-good-" + "g" * 30, "tok-dead-" + "d" * 30
    for t in (good, dead):
        await client.post("/v1/devices", headers=h, json={"fcm_token": t, "platform": "android"})
    a = await make_alert(app, uid, kind="news", recurring=True, params={"lead_minutes": 30})
    async with app.state.sessionmaker() as db:
        await evaluator.fire(db, await db.get(Alert, a), "k1", "T1", "B1", {"x": 1}, NOW)
        await db.commit()
        sender = FakeSender()
        sender.results[dead] = SendResult(False, unregistered=True)
        counts = await deliver_pending(db, sender, NOW)
        await db.commit()
    assert counts["partial"] == 0 and counts["sent"] == 1 and counts["removed_tokens"] == 1
    assert [d["token_hint"] for d in (await client.get("/v1/devices", headers=h)).json()] == [good[-6:]]

    async with app.state.sessionmaker() as db:
        await evaluator.fire(db, await db.get(Alert, a), "k2", "T2", "B2", {}, NOW)
        await db.commit()
        flaky = FakeSender()
        flaky.results[good] = SendResult(False, error="http 503")
        assert (await deliver_pending(db, flaky, NOW))["failed"] == 1
        await db.commit()
        assert (await deliver_pending(db, FakeSender(), NOW))["sent"] == 1  # retried
        await db.commit()
        await evaluator.fire(db, await db.get(Alert, a), "k3", "T3", "B3", {}, NOW)
        await db.commit()
        assert (await deliver_pending(db, DisabledSender(), NOW))["disabled"] == 1
        await db.commit()
    states = [e["delivery"] for e in (await client.get("/v1/alerts/events", headers=h)).json()["items"]]
    assert states == ["disabled", "sent", "sent"]


async def test_fcm_sender_http_v1() -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.host == "oauth2.googleapis.com":
            form = dict(x.split("=", 1) for x in request.content.decode().split("&"))
            claims = jwt.decode(form["assertion"], key.public_key(), algorithms=["RS256"],
                                audience="https://oauth2.googleapis.com/token")
            assert claims["iss"] == "push@proj.iam.gserviceaccount.com" and "firebase.messaging" in claims["scope"]
            return httpx.Response(200, json={"access_token": "ya29.test", "expires_in": 3600})
        assert request.headers["Authorization"] == "Bearer ya29.test"
        msg = json.loads(request.content)["message"]
        if msg["token"] == "dead":
            return httpx.Response(404, json={"error": {"status": "NOT_FOUND", "details": [
                {"@type": "type.googleapis.com/google.firebase.fcm.v1.FcmError", "errorCode": "UNREGISTERED"}]}})
        assert msg["notification"] == {"title": "T", "body": "B"} and msg["data"] == {"k": "v"}
        return httpx.Response(200, json={"name": "projects/proj/messages/1"})

    sender = FcmSender({"project_id": "proj", "client_email": "push@proj.iam.gserviceaccount.com",
                        "private_key": pem}, transport=httpx.MockTransport(handler))
    assert (await sender.send("live", "T", "B", {"k": "v"})).ok
    dead = await sender.send("dead", "T", "B", {"k": "v"})
    assert not dead.ok and dead.unregistered
    assert [r.url.host for r in seen].count("oauth2.googleapis.com") == 1  # access token cached
    assert "/v1/projects/proj/messages:send" in str(seen[1].url)


# ---- worker hook-up ---------------------------------------------------------------------------------------------

class FakeTwelveData:
    venue = "twelvedata"
    timeframes = frozenset({"15m", "1h"})

    def __init__(self, df: pd.DataFrame) -> None:
        self.df = df
        self.now = 0

    async def fetch_latest(self, venue_symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        if venue_symbol != "EUR/USD" or timeframe != "15m":
            return empty_frame()
        return self.df[self.df["time"] <= self.now].tail(limit).reset_index(drop=True)


async def test_worker_evaluates_alerts_publishes_events_and_pushes(
        app: FastAPI, client: httpx.AsyncClient, google: FakeGoogle, settings: Settings,
        fake_redis: fakeredis.FakeAsyncRedis, clock: Clock) -> None:
    clock.t = NOW.timestamp()  # the alert is created at 14:05; the crossing candle closes at 14:15
    h = await user(client, google)
    await client.post("/v1/devices", headers=h, json={"fcm_token": "tok-" + "z" * 30, "platform": "android"})
    df = flat(300, t_last=LAST_OPEN + 900)
    df.loc[299, ["high", "close"]] = [1.1012, 1.1010]
    r = await client.post("/v1/alerts", headers=h, json={
        "kind": "price_cross", "symbol": "EUR/USD", "params": {"level": 1.101, "direction": "above"}})
    assert r.status_code == 201
    feed = FakeTwelveData(df)
    sender = FakeSender()
    w = Worker(app.state.sessionmaker, fake_redis, {"twelvedata": feed}, PredictorCache(settings.artifacts_dir),
               settings, clock=clock, push=sender)
    pubsub = fake_redis.pubsub()
    await pubsub.subscribe(CHANNEL)

    # first tick: backfill (no alerts on history), then the next candle closes and crosses the level
    feed.now = clock.t = LAST_OPEN + 900 + 10  # candle LAST_OPEN closed; LAST_OPEN + 900 is forming
    first = await w.tick(clock.t)
    assert first.alerts == [] and first.ingested
    feed.now = clock.t = LAST_OPEN + 1800 + 10
    second = await w.tick(clock.t)
    assert len(second.alerts) == 1 and second.pushes["sent"] == 1
    assert sender.sent == [("tok-" + "z" * 30, "EUR/USD above 1.10100")]
    events = []
    for _ in range(50):  # the first message is the (ignored) subscribe confirmation
        m = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.01)
        if m is not None:
            events.append(json.loads(m["data"]))
    candles = [e for e in events if e["type"] == "candle" and e["symbol"] == "EUR/USD"]
    assert [e["candle"]["c"] for e in candles] == [1.1, 1.101]
    await pubsub.aclose()
    async with app.state.sessionmaker() as db:
        a = (await db.scalars(select(Alert))).one()
        assert a.active is False and a.trigger_count == 1


async def test_account_deletion_removes_phase3_user_data(app: FastAPI, client: httpx.AsyncClient,
                                                         google: FakeGoogle, clock: Clock) -> None:
    clock.t = NOW.timestamp()
    h = await user(client, google)
    wl = (await client.post("/v1/watchlists", headers=h, json={"name": "W", "symbols": ["EUR/USD"]})).json()
    await client.post("/v1/devices", headers=h, json={"fcm_token": "tok-" + "q" * 30, "platform": "android"})
    await client.put("/v1/me/risk-profile", headers=h, json={"balance": 1000})
    await client.post("/v1/alerts", headers=h, json={"kind": "news", "watchlist_id": wl["id"], "params": {}})
    await client.post("/v1/journal", headers=h, json={"symbol": "EUR/USD", "side": "long", "quantity": 1000,
                                                      "entry_price": 1.1, "entry_at": NOW.isoformat()})
    uid = await uid_of(app)
    async with app.state.sessionmaker() as db:
        await evaluator.fire(db, (await db.scalars(select(Alert))).one(), "k", "T", "B", {}, NOW)
        await db.commit()
    assert (await client.delete("/v1/me", headers=h)).status_code == 204
    for table in ("watchlists", "watchlist_items", "devices", "risk_profiles", "alerts", "alert_events",
                  "journal_entries"):
        assert await scalar(app, f"SELECT count(*) FROM {table}") == 0, table
    assert uid

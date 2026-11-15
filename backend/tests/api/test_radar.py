"""Market Radar over HTTP: ranking by conditions then activity, fields, symbols filter, errors."""

from __future__ import annotations

from datetime import timedelta

import httpx
from fastapi import FastAPI

from tests.api.conftest import Clock, scalar, seed_candles
from tests.api.test_tools import NOW, calendar_fresh, series


async def test_radar_ranks_markets_by_conditions_then_activity(app: FastAPI, client: httpx.AsyncClient,
                                                               clock: Clock) -> None:
    clock.t = NOW.timestamp()
    await seed_candles(app, "EUR/USD", "15m", series(600))
    await seed_candles(app, "GBP/USD", "15m", series(600, start=1.3, seed=5))
    await calendar_fresh(app, ("BoE Rate Decision", "GBP", "high", NOW + timedelta(minutes=10)))
    r = await client.get("/v1/radar", params={"symbols": "XAU/USD,GBP/USD,EUR/USD"})
    assert r.status_code == 200, r.text
    body = r.json()
    items = body["items"]
    assert [i["symbol"] for i in items] == ["EUR/USD", "GBP/USD", "XAU/USD"]
    assert [i["rank"] for i in items] == [1, 2, 3]
    eur, gbp, xau = items
    assert eur["light"] == "green" and eur["reasons"] == []
    assert gbp["light"] == "red" and gbp["news_state"] == "blackout"
    assert gbp["next_event"]["title"] == "BoE Rate Decision" and gbp["next_event_in_s"] == 600
    assert any("BoE" in reason or "blackout" in reason for reason in gbp["reasons"])
    assert xau["light"] == "unknown" and xau["reasons"] == ["no stored candles yet"] and xau["last_price"] is None
    assert eur["trend_regime"] in ("trending", "weak trend", "ranging") and eur["adx"] is not None
    assert 0 <= eur["volatility_percentile"] <= 100 and eur["volatility_regime"] == "normal"
    assert 2 <= len(eur["spark"]) <= 96 and eur["spark"][-1] == eur["last_price"]
    assert eur["change_24h_pct"] is not None and eur["price_decimals"] == 5
    assert "not a predicted direction" in body["ranking"]


async def test_radar_default_lists_ingested_markets_and_validates(app: FastAPI, client: httpx.AsyncClient,
                                                                  clock: Clock) -> None:
    clock.t = NOW.timestamp()
    expected = await scalar(app, """
        SELECT count(DISTINCT i.symbol) FROM ingestion_targets t
        JOIN instrument_listings l ON l.id = t.listing_id JOIN instruments i ON i.id = l.instrument_id
        WHERE t.timeframe = '15m' AND t.enabled AND l.is_primary""")
    r = await client.get("/v1/radar")
    assert r.status_code == 200 and len(r.json()["items"]) == min(expected, 30)
    r = await client.get("/v1/radar", params={"timeframe": "7m"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "unknown_timeframe"
    r = await client.get("/v1/radar", params={"symbols": "EUR/USD,NOPE/XYZ"})
    assert r.status_code == 422 and r.json()["error"]["details"] == ["NOPE/XYZ"]


async def test_radar_is_cached_briefly(app: FastAPI, client: httpx.AsyncClient, clock: Clock) -> None:
    """The radar is CPU-heavy and polled every minute: one computation serves everyone for radar_cache_s."""
    clock.t = NOW.timestamp()
    await seed_candles(app, "EUR/USD", "15m", series(600))
    first = (await client.get("/v1/radar", params={"symbols": "EUR/USD"})).json()["items"][0]["last_price"]
    await seed_candles(app, "EUR/USD", "15m", series(600, start=1.2))  # new prices arrive
    assert (await client.get("/v1/radar", params={"symbols": "EUR/USD"})).json()["items"][0]["last_price"] == first
    clock.t = NOW.timestamp() + app.state.settings.radar_cache_s + 1  # the cached result expired
    fresh = (await client.get("/v1/radar", params={"symbols": "EUR/USD"})).json()["items"][0]["last_price"]
    assert fresh != first


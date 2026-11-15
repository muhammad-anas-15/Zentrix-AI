"""GET /v1/patterns over HTTP: shape, honest labels, projection timing, errors."""

from __future__ import annotations

from datetime import datetime

import httpx
from fastapi import FastAPI

from tests.api.conftest import Clock, seed_candles
from tests.api.test_tools import NOW, series


async def test_pattern_projection_endpoint(app: FastAPI, client: httpx.AsyncClient, clock: Clock) -> None:
    clock.t = NOW.timestamp()
    await seed_candles(app, "EUR/USD", "15m", series(1300))
    r = await client.get("/v1/patterns", params={"symbol": "EUR/USD", "timeframe": "15m"})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["label"] == "Technical Pattern Projection (based on historical candlestick & ATR behaviour)"
    assert "not a prediction" in b["method"] and b["premium"]["feature"] == "pattern_outlook"
    assert b["history"] == 1300 and b["atr"] > 0
    assert b["structure"]["swing"] in ("uptrend", "downtrend", "range")
    proj = b["projection"]
    assert proj is not None and len(proj["steps"]) == 5 and proj["band"] == [0.2, 0.8]
    ats = [datetime.fromisoformat(s["at"]) for s in proj["steps"]]
    assert ats == sorted(ats) and (ats[1] - ats[0]).total_seconds() == 900
    assert datetime.fromisoformat(b["as_of"]) < ats[0]
    for s in proj["steps"]:
        assert s["band_low"] <= s["close"] <= s["band_high"] and s["low"] <= s["high"]
    if b["pattern"] is not None and b["pattern"]["bias"] != 0 and b["pattern"]["past_cases"]:
        br = b["base_rate"]
        assert 0 <= br["rate"] <= 1 and len(br["by_step"]) == 5 and isinstance(br["edge"], bool)

    r = await client.get("/v1/patterns", params={"symbol": "EUR/USD", "steps": 3})
    assert len(r.json()["projection"]["steps"]) == 3
    assert (await client.get("/v1/patterns", params={"symbol": "EUR/USD", "steps": 2})).status_code == 422
    r = await client.get("/v1/patterns", params={"symbol": "GBP/USD"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "no_data"

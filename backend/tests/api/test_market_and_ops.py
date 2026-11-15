"""Multi-asset reference data API, health/readiness."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

pytestmark = pytest.mark.db


async def instruments(client: httpx.AsyncClient, **params: object) -> dict:
    r = await client.get("/v1/instruments", params={"limit": 200, **params})
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


async def test_default_listing_shows_only_instruments_with_a_feed(client: httpx.AsyncClient) -> None:
    page = await instruments(client)
    by_class: dict[str, int] = {}
    for item in page["items"]:
        assert item["active"] and any(li["status"] == "active" for li in item["listings"])
        by_class[item["asset_class"]] = by_class.get(item["asset_class"], 0) + 1
    assert by_class == {"fx": 19, "metal": 1, "crypto": 20}
    assert page["total"] == 40


async def test_crypto_spot_and_perpetuals_are_separate_instruments(client: httpx.AsyncClient) -> None:
    perps = await instruments(client, asset_class="crypto", instrument_type="perpetual")
    assert perps["total"] == 10
    for item in perps["items"]:
        assert item["symbol"].endswith(":PERP") and item["settle"] == "USDT"
        assert [li["venue"] for li in item["listings"]] == ["binance_usdm"]
    spot = await instruments(client, venue="binance_spot")
    assert {i["symbol"] for i in spot["items"]} >= {"BTC/USDT", "ETH/USDT", "SOL/USDT"}
    assert all(i["instrument_type"] == "spot" for i in spot["items"])


async def test_metals_and_commodities_show_feed_status(client: httpx.AsyncClient) -> None:
    metals = {i["symbol"]: i for i in (await instruments(client, asset_class="metal", include_inactive=True))["items"]}
    assert set(metals) == {"XAU/USD", "XAG/USD", "XPT/USD", "XPD/USD"}
    assert metals["XAU/USD"]["active"] and metals["XAU/USD"]["listings"][0]["venue"] == "twelvedata"
    silver = metals["XAG/USD"]
    assert not silver["active"] and silver["listings"][0]["status"] == "restricted" and silver["listings"][0]["note"]
    assert metals["XPT/USD"]["listings"] == []
    commodities = await instruments(client, asset_class="commodity", include_inactive=True)
    assert commodities["total"] == 4 and not any(i["active"] for i in commodities["items"])


async def test_search_and_paging(client: httpx.AsyncClient) -> None:
    assert [i["symbol"] for i in (await instruments(client, q="xau"))["items"]] == ["XAU/USD"]
    assert (await instruments(client, q="yen"))["total"] >= 6  # JPY pairs by display name
    first = (await client.get("/v1/instruments", params={"limit": 5})).json()
    second = (await client.get("/v1/instruments", params={"limit": 5, "offset": 5})).json()
    assert len(first["items"]) == 5
    assert not {i["symbol"] for i in first["items"]} & {i["symbol"] for i in second["items"]}
    assert (await client.get("/v1/instruments", params={"limit": 500})).status_code == 422


async def test_timeframes_and_venues(client: httpx.AsyncClient) -> None:
    tfs = (await client.get("/v1/timeframes")).json()
    assert [t["code"] for t in tfs][0] == "1m" and tfs[-1]["code"] == "1w"
    assert {t["code"] for t in tfs} >= {"1m", "5m", "15m", "1h", "4h", "1d"}
    venues = {v["code"]: v["kind"] for v in (await client.get("/v1/venues")).json()}
    assert venues == {"binance_spot": "exchange", "binance_usdm": "exchange", "twelvedata": "data_vendor"}


async def test_health_and_readiness(client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    assert (await client.get("/health")).json()["status"] == "ok"
    r = await client.get("/ready")
    assert r.status_code == 200 and r.json()["checks"] == {"database": "ok", "redis": "ok"}

    async def down() -> None:
        raise ConnectionError("redis down")

    monkeypatch.setattr(app.state.redis, "ping", down)
    r = await client.get("/ready")
    assert r.status_code == 503 and r.json()["checks"]["redis"] == "unavailable"
    assert r.headers["X-Request-ID"]


async def test_openapi_lists_the_api(client: httpx.AsyncClient) -> None:
    spec = (await client.get("/openapi.json")).json()
    assert {"/v1/auth/google", "/v1/auth/refresh", "/v1/auth/logout", "/v1/auth/logout-all", "/v1/me",
            "/v1/instruments", "/v1/timeframes", "/v1/venues", "/health", "/ready"} <= set(spec["paths"])
    assert "Not financial advice" in spec["info"]["description"]
    assert set(spec["paths"]["/v1/me"]) == {"get", "patch", "delete"}

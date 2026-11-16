"""OWASP API1 (broken object-level authorization) and API5 (function level): a signed-in user can never read, edit or
delete another user's journal trades, watchlists, alerts or devices (404, so ids cannot be probed), and only admins
reach the admin API."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from tests.api.conftest import FakeGoogle, bearer, sign_in


async def test_users_cannot_touch_each_others_objects(client: httpx.AsyncClient, google: FakeGoogle) -> None:
    a = bearer(await sign_in(client, google, sub="owner-1", email="owner@example.com"))
    b = bearer(await sign_in(client, google, sub="intruder-1", email="intruder@example.com"))

    trade = (await client.post("/v1/journal", headers=a, json={
        "symbol": "EUR/USD", "side": "long", "quantity": 10000, "entry_price": 1.1, "stop_loss": 1.099,
        "entry_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat()})).json()
    wl = (await client.post("/v1/watchlists", headers=a, json={"name": "Mine", "symbols": ["EUR/USD"]})).json()
    alert = (await client.post("/v1/alerts", headers=a, json={
        "kind": "price_cross", "symbol": "EUR/USD", "params": {"level": 1.2, "direction": "above"}})).json()
    device = (await client.post("/v1/devices", headers=a, json={"fcm_token": "t" * 40, "platform": "android"})).json()
    assert all("id" in o for o in (trade, wl, alert, device)), (trade, wl, alert, device)

    attempts = [
        ("GET", f"/v1/journal/{trade['id']}", None), ("PATCH", f"/v1/journal/{trade['id']}", {"notes": "x"}),
        ("DELETE", f"/v1/journal/{trade['id']}", None),
        ("PATCH", f"/v1/watchlists/{wl['id']}", {"name": "Hijacked"}),
        ("POST", f"/v1/watchlists/{wl['id']}/items", {"symbol": "GBP/USD"}),
        ("GET", f"/v1/watchlists/{wl['id']}/quotes", None), ("DELETE", f"/v1/watchlists/{wl['id']}", None),
        ("GET", f"/v1/alerts/{alert['id']}", None), ("PATCH", f"/v1/alerts/{alert['id']}", {"active": False}),
        ("DELETE", f"/v1/alerts/{alert['id']}", None), ("DELETE", f"/v1/devices/{device['id']}", None),
        # an alert on someone else's watchlist
        ("POST", "/v1/alerts", {"kind": "signal", "watchlist_id": wl["id"], "params": {"min_strength": "Good"}}),
    ]
    for method, path, body in attempts:
        r = await client.request(method, path, headers=b, json=body)
        assert r.status_code == 404, (method, path, r.status_code, r.text)

    # the intruder's lists never contain the owner's objects
    for path in ("/v1/journal", "/v1/watchlists", "/v1/alerts", "/v1/devices", "/v1/alerts/events"):
        r = await client.get(path, headers=b)
        assert r.status_code == 200, (path, r.text)
        assert "Mine" not in r.text and "owner@example.com" not in r.text, path
    # and the owner still has everything
    assert (await client.get(f"/v1/journal/{trade['id']}", headers=a)).status_code == 200
    assert (await client.get(f"/v1/alerts/{alert['id']}", headers=a)).status_code == 200


async def test_admin_api_is_for_admins_only(client: httpx.AsyncClient, google: FakeGoogle) -> None:
    user = bearer(await sign_in(client, google, sub="plain-1", email="plain@example.com"))
    nobody = "00000000-0000-0000-0000-000000000000"
    for method, path in [("GET", "/v1/admin/users"), ("PUT", f"/v1/admin/users/{nobody}/plan")]:
        r = await client.request(method, path, headers=user, json={"plan": "premium"})
        assert r.status_code == 403, (path, r.text)
        assert (await client.request(method, path, json={"plan": "premium"})).status_code == 401

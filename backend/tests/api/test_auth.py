"""End-to-end auth flow against Postgres: Google sign-in, refresh rotation, reuse detection, logout(-all),
profile updates, account deletion, rate limiting, error shape."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI

from app.core.config import Settings
from app.core.security import create_access_token, subject_hash
from tests.api.conftest import FakeGoogle, bearer, scalar, sign_in

pytestmark = pytest.mark.db


async def refresh(client: httpx.AsyncClient, token: str) -> httpx.Response:
    return await client.post("/v1/auth/refresh", json={"refresh_token": token})


async def test_sign_in_creates_account_and_me_works(client: httpx.AsyncClient, google: FakeGoogle,
                                                    app: FastAPI) -> None:
    body = await sign_in(client, google)
    assert body["token_type"] == "bearer" and body["expires_in"] == 900
    user = body["user"]
    assert user["email"] == "trader@example.com" and user["plan"] == "free" and user["locale"] == "en"
    assert user["premium_access"] is True  # PREMIUM_ENFORCED=false: everyone can use premium features
    me = await client.get("/v1/me", headers=bearer(body))
    assert me.status_code == 200 and me.json()["id"] == user["id"]
    assert await scalar(app, "SELECT count(*) FROM auth_identities WHERE provider = 'google'") == 1
    assert await scalar(app, "SELECT event FROM audit_log") == "user_created"
    # only the hash of the refresh token is stored
    assert await scalar(app, "SELECT count(*) FROM refresh_tokens WHERE token_hash = :t",
                        t=body["refresh_token"]) == 0


async def test_second_sign_in_reuses_account(client: httpx.AsyncClient, google: FakeGoogle, app: FastAPI) -> None:
    first = await sign_in(client, google)
    second = await sign_in(client, google, email="renamed@example.com")
    assert first["user"]["id"] == second["user"]["id"]
    assert second["user"]["email"] == "renamed@example.com"
    assert await scalar(app, "SELECT count(*) FROM users") == 1
    other = await sign_in(client, google, sub="google-sub-2", email="other@example.com")
    assert other["user"]["id"] != first["user"]["id"]


@pytest.mark.parametrize(("claims", "code"), [
    ({"aud": "someone-elses-client-id"}, "invalid_google_token"),
    ({"iss": "https://evil.example.com"}, "invalid_google_token"),
    ({"exp_in": -300}, "google_token_expired"),
    ({"email_verified": False}, "email_not_verified"),
    ({"kid": "unknown-key"}, "invalid_google_token"),
])
async def test_rejects_invalid_google_tokens(client: httpx.AsyncClient, google: FakeGoogle, app: FastAPI,
                                             claims: dict, code: str) -> None:
    r = await client.post("/v1/auth/google", json={"id_token": google.token(**claims)})
    assert r.status_code == 401 and r.json()["error"]["code"] == code
    assert await scalar(app, "SELECT count(*) FROM users") == 0


async def test_rejects_token_signed_by_another_key_and_garbage(client: httpx.AsyncClient, google: FakeGoogle) -> None:
    forged = google.token(key=rsa.generate_private_key(public_exponent=65537, key_size=2048))
    r = await client.post("/v1/auth/google", json={"id_token": forged})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_google_token"
    r = await client.post("/v1/auth/google", json={"id_token": "not-a-jwt-at-all-but-long-enough"})
    assert r.status_code == 401


async def test_refresh_rotates_and_reuse_revokes_the_family(client: httpx.AsyncClient, google: FakeGoogle,
                                                            app: FastAPI) -> None:
    s = await sign_in(client, google)
    r1 = await refresh(client, s["refresh_token"])
    assert r1.status_code == 200
    rotated = r1.json()
    assert rotated["refresh_token"] != s["refresh_token"]
    assert (await client.get("/v1/me", headers=bearer(rotated))).status_code == 200

    replay = await refresh(client, s["refresh_token"])  # stolen/replayed old token
    assert replay.status_code == 401 and replay.json()["error"]["code"] == "refresh_token_reused"
    after = await refresh(client, rotated["refresh_token"])  # the legitimate successor is revoked too
    assert after.status_code == 401
    assert await scalar(app, "SELECT count(*) FROM refresh_tokens WHERE revoked_at IS NULL") == 0
    assert await scalar(app, "SELECT count(*) FROM audit_log WHERE event = 'refresh_token_reuse'") >= 1


async def test_refresh_rejects_unknown_and_expired(client: httpx.AsyncClient, google: FakeGoogle,
                                                   app: FastAPI) -> None:
    r = await refresh(client, "x" * 43)
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_refresh_token"
    s = await sign_in(client, google)
    async with app.state.engine.begin() as conn:
        from sqlalchemy import text
        await conn.execute(text("UPDATE refresh_tokens SET expires_at = now() - interval '1 minute'"))
    r = await refresh(client, s["refresh_token"])
    assert r.status_code == 401 and r.json()["error"]["code"] == "refresh_token_expired"


async def test_logout_revokes_this_session_only(client: httpx.AsyncClient, google: FakeGoogle) -> None:
    phone = await sign_in(client, google, device="phone")
    tablet = await sign_in(client, google, device="tablet")
    assert (await client.post("/v1/auth/logout", json={"refresh_token": phone["refresh_token"]})).status_code == 204
    assert (await client.post("/v1/auth/logout", json={"refresh_token": phone["refresh_token"]})).status_code == 204
    assert (await refresh(client, phone["refresh_token"])).status_code == 401
    assert (await refresh(client, tablet["refresh_token"])).status_code == 200


async def test_logout_all_revokes_refresh_and_access_tokens(client: httpx.AsyncClient, google: FakeGoogle) -> None:
    phone = await sign_in(client, google, device="phone")
    tablet = await sign_in(client, google, device="tablet")
    assert (await client.post("/v1/auth/logout-all", headers=bearer(phone))).status_code == 204
    for session in (phone, tablet):
        r = await client.get("/v1/me", headers=bearer(session))
        assert r.status_code == 401 and r.json()["error"]["code"] == "token_revoked"
        assert (await refresh(client, session["refresh_token"])).status_code == 401
    fresh = await sign_in(client, google)  # signing in again works immediately
    assert (await client.get("/v1/me", headers=bearer(fresh))).status_code == 200


async def test_bad_access_tokens(client: httpx.AsyncClient, google: FakeGoogle, settings: Settings) -> None:
    s = await sign_in(client, google)
    assert (await client.get("/v1/me")).json()["error"]["code"] == "unauthorized"
    tampered = s["access_token"][:-4] + ("AAAA" if not s["access_token"].endswith("AAAA") else "BBBB")
    assert (await client.get("/v1/me", headers=bearer(tampered))).json()["error"]["code"] == "invalid_token"
    old, _ = create_access_token(settings, uuid.UUID(s["user"]["id"]), 0, now=datetime.now(UTC) - timedelta(hours=1))
    r = await client.get("/v1/me", headers=bearer(old))
    assert r.status_code == 401 and r.json()["error"]["code"] == "token_expired"
    assert (await client.get("/v1/me", headers=bearer(s["refresh_token"]))).status_code == 401


async def test_update_profile(client: httpx.AsyncClient, google: FakeGoogle) -> None:
    s = await sign_in(client, google)
    r = await client.patch("/v1/me", headers=bearer(s),
                           json={"locale": "ur", "timezone": "Asia/Karachi", "display_name": "Anas"})
    assert r.status_code == 200
    assert (r.json()["locale"], r.json()["timezone"], r.json()["display_name"]) == ("ur", "Asia/Karachi", "Anas")
    bad = await client.patch("/v1/me", headers=bearer(s), json={"locale": "fr"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "validation_error"
    assert (await client.patch("/v1/me", headers=bearer(s), json={"timezone": "Mars/Base"})).status_code == 422


async def test_delete_account_removes_everything(client: httpx.AsyncClient, google: FakeGoogle, app: FastAPI,
                                                 settings: Settings) -> None:
    s = await sign_in(client, google)
    await client.patch("/v1/me", headers=bearer(s), json={"display_name": "Gone Soon"})
    user_id = uuid.UUID(s["user"]["id"])
    assert (await client.delete("/v1/me", headers=bearer(s))).status_code == 204

    assert (await client.get("/v1/me", headers=bearer(s))).status_code == 401
    assert (await refresh(client, s["refresh_token"])).status_code == 401
    for table in ("users", "auth_identities", "refresh_tokens", "devices", "subscriptions", "entitlements"):
        assert await scalar(app, f"SELECT count(*) FROM {table}") == 0, table
    assert await scalar(app, "SELECT count(*) FROM audit_log WHERE user_id IS NOT NULL") == 0
    deleted_hash = await scalar(app, "SELECT subject_hash FROM audit_log WHERE event = 'account_deleted'")
    assert deleted_hash == subject_hash(settings, user_id)
    assert await scalar(app, "SELECT count(*) FROM audit_log WHERE meta::text LIKE '%example.com%'") == 0

    again = await sign_in(client, google)  # same Google account can come back as a brand-new user
    assert again["user"]["id"] != s["user"]["id"] and again["user"]["display_name"] == "Test Trader"


async def test_sign_in_is_rate_limited(client: httpx.AsyncClient, google: FakeGoogle, settings: Settings) -> None:
    limit, _ = Settings.parse_limit(settings.rate_limit_auth)
    token = google.token()
    for _ in range(limit):
        assert (await client.post("/v1/auth/google", json={"id_token": token})).status_code == 200
    r = await client.post("/v1/auth/google", json={"id_token": token})
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["Retry-After"]) >= 1


async def test_error_shape(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/does-not-exist")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    r = await client.post("/v1/auth/google", json={})
    assert r.status_code == 422 and r.json()["error"]["details"]

"""Phase 6 hardening over HTTP: 500s without stack traces, security headers, request size limit, request ids,
metrics access, API docs off when deployed, secrets from files, Sentry scrubbing."""

from __future__ import annotations

from pathlib import Path

import fakeredis
import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings, load_settings
from app.core.observability import scrub
from app.main import create_app
from tests.api.conftest import CLIENT_ID, bearer, sign_in
from tests.api.conftest import FakeGoogle as FakeGoogleT


def deployed(settings: Settings, **extra: object) -> Settings:
    return settings.model_copy(update={"app_env": "staging", "jwt_secret": settings.jwt_secret,
                                       "google_client_ids": [CLIENT_ID], **extra})


async def test_security_headers_and_request_ids(client: httpx.AsyncClient, google: FakeGoogleT) -> None:
    r = await client.get("/v1/timeframes")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert "cache-control" not in r.headers  # public data may be cached
    assert "strict-transport-security" not in r.headers  # only when deployed behind TLS
    r = await client.get("/v1/timeframes", headers={"X-Request-ID": "abc12345-good"})
    assert r.headers["x-request-id"] == "abc12345-good"
    r = await client.get("/v1/timeframes", headers={"X-Request-ID": 'evil"\n{"injected":1}'})
    assert r.headers["x-request-id"] != 'evil"\n{"injected":1}' and len(r.headers["x-request-id"]) == 32
    tokens = await sign_in(client, google)
    r = await client.get("/v1/me", headers=bearer(tokens))
    assert r.headers["cache-control"] == "no-store"  # personal data


async def test_large_or_malformed_bodies_are_refused(client: httpx.AsyncClient, app: FastAPI) -> None:
    big = b"x" * (app.state.settings.max_body_bytes + 1)
    r = await client.post("/v1/risk/position-size", content=big, headers={"Content-Type": "application/json"})
    assert r.status_code == 413 and r.json()["error"]["code"] == "payload_too_large"
    r = await client.post("/v1/risk/position-size", content=b"{}",
                          headers={"Content-Type": "application/json", "Content-Length": "abc"})
    assert r.status_code == 400


async def test_unhandled_errors_are_json_without_internals(app: FastAPI, client: httpx.AsyncClient,
                                                           monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.v1 import market

    async def boom(*_: object, **__: object) -> None:
        raise RuntimeError("database password is hunter2")

    monkeypatch.setattr(market, "chart_timeframes", boom)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/v1/instruments")
    assert r.status_code == 500
    body = r.json()
    assert body["error"]["code"] == "internal_error" and "hunter2" not in r.text and "Traceback" not in r.text
    assert len(body["error"]["details"]["request_id"]) == 32


async def test_metrics_are_counted_and_protected(app: FastAPI, client: httpx.AsyncClient) -> None:
    await client.get("/v1/timeframes")
    r = await client.get("/metrics")  # dev/test without a token: open
    assert r.status_code == 200
    assert 'zentrix_http_requests_total{method="GET",route="/v1/timeframes",status="200"}' in r.text
    settings = app.state.settings
    original = settings.metrics_token
    settings.metrics_token = type(original)("s3cret-token")
    try:
        assert (await client.get("/metrics")).status_code == 401
        assert (await client.get("/metrics", headers={"Authorization": "Bearer wrong"})).status_code == 401
        assert (await client.get("/metrics", headers={"Authorization": "Bearer s3cret-token"})).status_code == 200
    finally:
        settings.metrics_token = original


async def test_deployed_app_hides_docs_and_metrics_and_sets_hsts(settings: Settings,
                                                                 fake_redis: fakeredis.FakeAsyncRedis) -> None:
    app = create_app(deployed(settings), redis=fake_redis)
    async with (app.router.lifespan_context(app),
                httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c):
        assert (await c.get("/docs")).status_code == 404
        assert (await c.get("/openapi.json")).status_code == 404
        assert (await c.get("/metrics")).status_code == 404  # no METRICS_TOKEN: not exposed
        r = await c.get("/health")
        assert r.status_code == 200 and r.json()["env"] == "staging"
        assert r.headers["strict-transport-security"].startswith("max-age=31536000")
        assert (await c.post("/v1/auth/dev", json={"email": "a@b.c"})).status_code == 404


def test_secrets_can_come_from_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "jwt_secret").write_text("j" * 40)
    (tmp_path / "metrics_token").write_text("from-file")
    monkeypatch.setenv("SECRETS_DIR", str(tmp_path))
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("METRICS_TOKEN", raising=False)
    s = load_settings()
    assert s.jwt_secret.get_secret_value() == "j" * 40 and s.metrics_token.get_secret_value() == "from-file"
    monkeypatch.setenv("METRICS_TOKEN", "from-env")  # the environment wins over a file
    assert load_settings().metrics_token.get_secret_value() == "from-env"


def test_sentry_events_carry_no_personal_data() -> None:
    event = {"request": {"url": "https://api/x", "headers": {"Authorization": "Bearer t", "Cookie": "c=1",
                                                            "User-Agent": "app"},
                         "query_string": "token=1", "cookies": {"c": "1"}, "data": {"email": "a@b.c"}},
             "user": {"ip_address": "1.2.3.4", "email": "a@b.c"}}
    out = scrub(event)
    assert out["request"]["headers"] == {"Authorization": "[removed]", "Cookie": "[removed]", "User-Agent": "app"}
    assert "query_string" not in out["request"] and "cookies" not in out["request"] and "data" not in out["request"]
    assert "user" not in out


def test_staging_refuses_weak_secrets(settings: Settings) -> None:
    with pytest.raises(ValueError, match="JWT_SECRET"):
        Settings(_env_file=None, app_env="staging", database_url=settings.database_url,  # type: ignore[call-arg]
                 google_client_ids=[CLIENT_ID], jwt_secret="short", audit_salt="s" * 24)
    with pytest.raises(ValueError, match="DEV_LOGIN"):
        Settings(_env_file=None, app_env="prod", dev_login=True, jwt_secret="t" * 48,  # type: ignore[call-arg]
                 google_client_ids=[CLIENT_ID], audit_salt="s" * 24)

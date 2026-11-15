"""Developer sign-in: only mounted with APP_ENV=dev/test and DEV_LOGIN=true; refused by the settings elsewhere."""

from __future__ import annotations

from collections.abc import AsyncIterator

import fakeredis
import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.main import create_app
from app.services.auth.google import GoogleTokenVerifier
from tests.api.conftest import CLIENT_ID, bearer, scalar

pytestmark = pytest.mark.db


@pytest.fixture
async def dev_client(settings: Settings, fake_redis: fakeredis.FakeAsyncRedis) -> AsyncIterator[httpx.AsyncClient]:
    async def no_jwks() -> dict:
        return {"keys": []}

    application = create_app(settings.model_copy(update={"dev_login": True}), redis=fake_redis,
                             google_verifier=GoogleTokenVerifier([CLIENT_ID], no_jwks))
    transport = httpx.ASGITransport(app=application)
    async with application.router.lifespan_context(application), \
            httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_dev_login_is_not_mounted_by_default(client: httpx.AsyncClient) -> None:
    r = await client.post("/v1/auth/dev", json={"email": "dev@example.com"})
    assert r.status_code == 404


async def test_dev_login_issues_a_normal_session(dev_client: httpx.AsyncClient, app: FastAPI) -> None:
    r = await dev_client.post("/v1/auth/dev", json={"email": "Dev@Example.com", "device_name": "emulator"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["email"] == "dev@example.com" and body["user"]["display_name"] == "dev"
    assert (await dev_client.get("/v1/me", headers=bearer(body))).status_code == 200
    again = (await dev_client.post("/v1/auth/dev", json={"email": "dev@example.com"})).json()
    assert again["user"]["id"] == body["user"]["id"]  # same identity, same account
    assert await scalar(app, "SELECT count(*) FROM auth_identities WHERE provider = 'dev'") == 1
    refreshed = await dev_client.post("/v1/auth/refresh", json={"refresh_token": body["refresh_token"]})
    assert refreshed.status_code == 200
    assert (await dev_client.post("/v1/auth/dev", json={"email": "not-an-email"})).status_code == 422


@pytest.mark.parametrize("env", ["staging", "prod"])
def test_settings_refuse_dev_login_outside_dev(env: str) -> None:
    with pytest.raises(ValueError, match="DEV_LOGIN"):
        Settings(_env_file=None, app_env=env, dev_login=True, jwt_secret="x" * 40,  # type: ignore[call-arg]
                 google_client_ids=["a"], audit_salt="s" * 20)

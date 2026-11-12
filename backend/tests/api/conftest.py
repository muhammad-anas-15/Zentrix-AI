"""API tests run against a real PostgreSQL 16 (started via pgserver; no Docker) migrated with Alembic, fakeredis,
and a fake Google: RS256 ID tokens signed by a local key whose JWKS the verifier is given."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import fakeredis
import httpx
import jwt
import pgserver
import pytest
from alembic.config import Config
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from fastapi import FastAPI
from sqlalchemy import text

from alembic import command
from app.core.config import Settings
from app.main import create_app
from app.services.auth.google import GoogleTokenVerifier

BACKEND = Path(__file__).resolve().parents[2]
CLIENT_ID = "test-client.apps.googleusercontent.com"
KID = "test-key-1"
logging.getLogger("pgserver").setLevel(logging.WARNING)  # its atexit log hits a closed stream


def make_database(srv: pgserver.PostgresServer, name: str) -> str:
    srv.psql(f"DROP DATABASE IF EXISTS {name} WITH (FORCE);")
    srv.psql(f"CREATE DATABASE {name};")
    base = srv.get_uri().rpartition("/")[0].replace("postgresql://", "postgresql+asyncpg://", 1)
    return f"{base}/{name}"


def alembic_config(url: str) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["skip_logging_config"] = True
    return cfg


async def alembic(url: str, action: str, target: str) -> None:
    # env.py runs its own event loop, so run Alembic in a worker thread.
    await asyncio.to_thread(getattr(command, action), alembic_config(url), target)


@pytest.fixture(scope="session")
def pg(tmp_path_factory: pytest.TempPathFactory) -> Iterator[pgserver.PostgresServer]:
    srv = pgserver.get_server(tmp_path_factory.mktemp("pgdata"), cleanup_mode="stop")
    yield srv
    srv.cleanup()


@pytest.fixture(scope="session")
async def db_url(pg: pgserver.PostgresServer) -> str:
    url = make_database(pg, "zentrix_test")
    await alembic(url, "upgrade", "head")
    return url


@pytest.fixture(scope="session")
def google_key() -> RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FakeGoogle:
    """Issues Google-shaped ID tokens signed with a test key."""

    def __init__(self, key: RSAPrivateKey) -> None:
        self.key = key

    def jwks(self) -> dict[str, Any]:
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        return {"keys": [{**jwk, "kid": KID, "alg": "RS256", "use": "sig"}]}

    def token(self, sub: str = "google-sub-1", email: str = "trader@example.com", aud: str = CLIENT_ID,
              iss: str = "https://accounts.google.com", exp_in: int = 3600, email_verified: bool = True,
              kid: str = KID, key: RSAPrivateKey | None = None, name: str = "Test Trader") -> str:
        now = int(time.time())
        claims = {"iss": iss, "aud": aud, "sub": sub, "email": email, "email_verified": email_verified,
                  "name": name, "iat": now, "exp": now + exp_in}
        return jwt.encode(claims, key or self.key, algorithm="RS256", headers={"kid": kid})


@pytest.fixture(scope="session")
def google(google_key: RSAPrivateKey) -> FakeGoogle:
    return FakeGoogle(google_key)


@pytest.fixture(scope="session")
def settings(db_url: str) -> Settings:
    return Settings(_env_file=None, app_env="test", database_url=db_url,  # type: ignore[call-arg]
                    google_client_ids=[CLIENT_ID], jwt_secret="t" * 48, audit_salt="s" * 24,
                    rate_limit_auth="20/60", rate_limit_refresh="50/60", rate_limit_public="300/60",
                    rate_limit_user="500/60")


@pytest.fixture(scope="session")
def fake_redis() -> fakeredis.FakeAsyncRedis:
    return fakeredis.FakeAsyncRedis()


@pytest.fixture(scope="session")
async def app(settings: Settings, fake_redis: fakeredis.FakeAsyncRedis, google: FakeGoogle) -> AsyncIterator[FastAPI]:
    async def fetch_jwks() -> dict[str, Any]:
        return google.jwks()

    application = create_app(settings, redis=fake_redis,
                             google_verifier=GoogleTokenVerifier([CLIENT_ID], fetch_jwks))
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture(scope="session")
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
async def _clean(app: FastAPI, fake_redis: fakeredis.FakeAsyncRedis) -> AsyncIterator[None]:
    yield
    async with app.state.engine.begin() as conn:
        await conn.execute(text("TRUNCATE users, audit_log RESTART IDENTITY CASCADE"))
        await conn.execute(text("TRUNCATE signal_outcomes, signals, model_versions, candles RESTART IDENTITY CASCADE"))
        await conn.execute(text("DELETE FROM ingestion_targets WHERE reason <> 'chart'"))
        await conn.execute(text("UPDATE ingestion_targets SET enabled = true"))
    await fake_redis.flushall()


async def scalar(app: FastAPI, sql: str, **params: Any) -> Any:
    async with app.state.engine.connect() as conn:
        return (await conn.execute(text(sql), params)).scalar()


async def sign_in(client: httpx.AsyncClient, google: FakeGoogle, device: str = "pixel-8", **claims: Any) -> dict:
    r = await client.post("/v1/auth/google", json={"id_token": google.token(**claims), "device_name": device})
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


def bearer(tokens: dict | str) -> dict[str, str]:
    token = tokens if isinstance(tokens, str) else tokens["access_token"]
    return {"Authorization": f"Bearer {token}"}

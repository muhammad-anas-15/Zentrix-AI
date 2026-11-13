"""scripts.dev_api: the environment it gives the local API used by the app."""

from __future__ import annotations

from app.core.config import Settings
from scripts.dev_api import dev_env


def test_dev_env_enables_developer_sign_in_and_cors_for_the_web_build() -> None:
    env = dev_env("postgresql+asyncpg://postgres:@127.0.0.1:5555/zentrix", 8090)
    assert env["APP_ENV"] == "dev" and env["DEV_LOGIN"] == "true"
    s = Settings(_env_file=None, app_env=env["APP_ENV"], dev_login=True,  # type: ignore[call-arg]
                 cors_origins=env["CORS_ORIGINS"], database_url=env["DATABASE_URL"])
    assert s.cors_origins == ["http://localhost:8090", "http://127.0.0.1:8090"]
    assert s.dev_login and s.app_env == "dev"

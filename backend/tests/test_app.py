"""Settings behaviour (no database needed). API behaviour is covered in tests/api against Postgres."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.core.security import create_access_token, decode_access_token


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("GEMINI_API_KEY", "abc")
    monkeypatch.setenv("GOOGLE_CLIENT_IDS", "android.apps.googleusercontent.com, web.apps.googleusercontent.com")
    get_settings.cache_clear()
    s = get_settings()
    assert s.app_env == "test" and s.gemini_api_key.get_secret_value() == "abc"
    assert s.google_client_ids == ["android.apps.googleusercontent.com", "web.apps.googleusercontent.com"]
    assert "abc" not in repr(s)  # secrets are masked in logs/reprs
    get_settings.cache_clear()


def test_premium_not_enforced_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PREMIUM_ENFORCED", raising=False)
    assert Settings(_env_file=None).premium_enforced is False  # type: ignore[call-arg]


@pytest.mark.parametrize("env", ["staging", "prod"])
def test_production_refuses_to_start_without_secrets(env: str) -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(_env_file=None, app_env=env)  # type: ignore[call-arg]
    with pytest.raises(ValidationError, match="GOOGLE_CLIENT_IDS"):
        Settings(_env_file=None, app_env=env, jwt_secret="x" * 40)  # type: ignore[call-arg]
    ok = Settings(_env_file=None, app_env=env, jwt_secret="x" * 40, google_client_ids=["a"],  # type: ignore[call-arg]
                  audit_salt="y" * 20)
    assert ok.app_env == env


def test_dev_gets_ephemeral_secret_and_tokens_round_trip() -> None:
    import uuid

    s = Settings(_env_file=None, app_env="dev")  # type: ignore[call-arg]
    assert len(s.jwt_secret.get_secret_value()) >= 32
    uid = uuid.uuid4()
    token, ttl = create_access_token(s, uid, version=3)
    claims = decode_access_token(s, token)
    assert (claims.user_id, claims.version, ttl) == (uid, 3, 900)
    other = Settings(_env_file=None, app_env="dev")  # type: ignore[call-arg]
    with pytest.raises(Exception, match="Invalid access token"):
        decode_access_token(other, token)  # different secret

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import app


def test_health() -> None:
    r = TestClient(app).get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("GEMINI_API_KEY", "abc")
    get_settings.cache_clear()
    s = get_settings()
    assert s.app_env == "test" and s.gemini_api_key.get_secret_value() == "abc"
    assert "abc" not in repr(s)  # secrets are masked in logs/reprs
    get_settings.cache_clear()


def test_premium_not_enforced_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PREMIUM_ENFORCED", raising=False)
    assert Settings(_env_file=None).premium_enforced is False  # type: ignore[call-arg]

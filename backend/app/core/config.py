"""Application settings (Pydantic v2). Secrets come from the environment / backend/.env only."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from ml.settings import BACKEND_DIR


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    app_env: Literal["dev", "test", "staging", "prod"] = "dev"
    database_url: str = "postgresql+asyncpg://zentrix:zentrix@localhost:5432/zentrix"
    redis_url: str = "redis://localhost:6379/0"
    gemini_api_key: SecretStr = SecretStr("")
    # Billing is out of scope: while False, premium features are unlocked for every user.
    premium_enforced: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()

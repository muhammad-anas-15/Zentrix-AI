"""Application settings (Pydantic v2). Secrets come from the environment / backend/.env only."""

from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from ml.settings import BACKEND_DIR

CsvList = Annotated[list[str], NoDecode]


class Settings(BaseSettings):
    # env_ignore_empty: "KEY=" in .env means "use the default", never an empty value
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore", env_ignore_empty=True)

    app_env: Literal["dev", "test", "staging", "prod"] = "dev"
    log_json: bool = False  # JSON logs (set true outside dev)
    database_url: str = "postgresql+asyncpg://zentrix:zentrix@localhost:5432/zentrix"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: CsvList = Field(default_factory=list)
    trust_proxy_headers: bool = False  # use X-Forwarded-For only behind a trusted proxy

    # Auth
    jwt_secret: SecretStr = SecretStr("")
    jwt_issuer: str = "zentrix-api"
    jwt_audience: str = "zentrix-app"
    access_token_ttl_s: int = 15 * 60
    refresh_token_ttl_s: int = 30 * 86400
    google_client_ids: CsvList = Field(default_factory=list)  # Android / iOS / web OAuth client IDs
    google_jwks_url: str = "https://www.googleapis.com/oauth2/v3/certs"
    audit_salt: SecretStr = SecretStr("")

    # Rate limits: "count/seconds"
    rate_limit_enabled: bool = True
    rate_limit_auth: str = "10/60"  # per IP, sign-in
    rate_limit_refresh: str = "30/60"  # per IP
    rate_limit_public: str = "120/60"  # per IP, unauthenticated reads
    rate_limit_user: str = "240/60"  # per user

    gemini_api_key: SecretStr = SecretStr("")
    # Billing is out of scope: while False, premium features are unlocked for every user.
    premium_enforced: bool = False

    # Worker (candle ingestion, signals, outcomes)
    artifacts_dir: Path = BACKEND_DIR / "ml" / "artifacts"  # same env var as ml.settings (ARTIFACTS_DIR)
    worker_poll_s: float = 5.0
    ingest_grace_s: float = 10.0  # wait this long after a candle closes before fetching it
    ingest_retry_s: float = 30.0  # min seconds between attempts for the same series
    twelve_data_daily_budget: int = 780  # free plan: 800 requests/day
    twelve_data_min_live_tf_s: int = 900  # below 15m the free plan cannot keep up
    signal_max_lag_s: int | None = None  # default: one timeframe after the candle closes
    outcome_void_after_s: int = 6 * 3600  # missing candles this long after the expected exit -> void

    @field_validator("cors_origins", "google_client_ids", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @model_validator(mode="after")
    def _check_secrets(self) -> Settings:
        if self.app_env in ("staging", "prod"):
            if len(self.jwt_secret.get_secret_value()) < 32:
                raise ValueError("JWT_SECRET must be set (>= 32 chars) outside dev/test")
            if not self.google_client_ids:
                raise ValueError("GOOGLE_CLIENT_IDS must be set outside dev/test")
            if len(self.audit_salt.get_secret_value()) < 16:
                raise ValueError("AUDIT_SALT must be set (>= 16 chars) outside dev/test")
        else:
            # dev/test: ephemeral secrets so the app starts; tokens die with the process.
            if not self.jwt_secret.get_secret_value():
                self.jwt_secret = SecretStr(secrets.token_urlsafe(48))
            if not self.audit_salt.get_secret_value():
                self.audit_salt = SecretStr(secrets.token_urlsafe(24))
        return self

    @staticmethod
    def parse_limit(spec: str) -> tuple[int, int]:
        count, seconds = spec.split("/")
        return int(count), int(seconds)


@lru_cache
def get_settings() -> Settings:
    return Settings()

"""ML package settings. Read from the environment (and backend/.env) only; never hardcode secrets."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent


class MLSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore", env_ignore_empty=True)

    twelve_data_api_key: SecretStr = SecretStr("")
    twelve_data_min_interval_s: float = 8.0  # free plan: 8 requests/minute
    data_cache_dir: Path = BACKEND_DIR / "data_cache"
    artifacts_dir: Path = BACKEND_DIR / "ml" / "artifacts"
    predictions_db: Path = BACKEND_DIR / "data_cache" / "demo_trading_log.sqlite3"
    ml_report_path: Path = REPO_DIR / "docs" / "ML_REPORT.md"


@lru_cache
def get_settings() -> MLSettings:
    return MLSettings()

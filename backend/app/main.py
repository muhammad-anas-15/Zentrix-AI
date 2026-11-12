"""FastAPI entry point. Phase 0 exposes only a liveness probe; the API is built in Phase 1."""

from __future__ import annotations

from fastapi import FastAPI

from app.core.config import get_settings

DISCLAIMER = "Not financial advice."

app = FastAPI(title="Zentrix API", version="0.1.0", description=f"Trading analysis assistant. {DISCLAIMER}")


@app.get("/health", tags=["ops"])
def health() -> dict[str, str]:
    return {"status": "ok", "env": get_settings().app_env}

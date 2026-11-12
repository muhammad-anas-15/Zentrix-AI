"""FastAPI application factory. ``app`` is the ASGI entry point (uvicorn app.main:app)."""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from app.api import health
from app.api.v1 import auth, market, me, signals
from app.core.config import Settings, get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging, get_logger
from app.core.ratelimit import RateLimiter
from app.db.session import make_engine, make_sessionmaker
from app.services.auth.google import GoogleTokenVerifier, http_jwks_fetcher

VERSION = "0.3.0"
DESCRIPTION = """Zentrix: trading analysis and risk tools for FX, metals, commodities and crypto.

**Not financial advice.** Signals are probabilities based on past data, not guarantees. Accuracy figures come
only from the out-of-sample track record."""

log = get_logger("app")


def create_app(settings: Settings | None = None, *, redis: Redis | None = None,
               google_verifier: GoogleTokenVerifier | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(json=settings.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = make_engine(settings.database_url)
        app.state.settings = settings
        app.state.engine = engine
        app.state.sessionmaker = make_sessionmaker(engine)
        # Short timeouts: if Redis is down, rate limiting fails open fast instead of stalling every request.
        app.state.redis = redis or Redis.from_url(settings.redis_url, socket_connect_timeout=0.25, socket_timeout=0.5)
        app.state.rate_limiter = RateLimiter(app.state.redis)
        app.state.google_verifier = google_verifier or GoogleTokenVerifier(
            settings.google_client_ids, http_jwks_fetcher(settings.google_jwks_url))
        try:
            yield
        finally:
            await engine.dispose()
            if redis is None:
                await app.state.redis.aclose()

    app = FastAPI(title="Zentrix API", version=VERSION, description=DESCRIPTION, lifespan=lifespan,
                  openapi_tags=[{"name": "auth", "description": "Google sign-in and sessions"},
                                {"name": "account", "description": "Profile, preferences, account deletion"},
                                {"name": "market", "description": "Instruments, venues, timeframes, candles"},
                                {"name": "signals", "description": "Live signals, outcomes, track record, models"},
                                {"name": "ops", "description": "Health checks"}])
    install_error_handlers(app)
    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"],
                           allow_headers=["Authorization", "Content-Type"])

    @app.middleware("http")
    async def request_context(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        structlog.contextvars.bind_contextvars(request_id=request_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()
        response.headers["X-Request-ID"] = request_id
        # Path only (no query string, headers or bodies): tokens never reach the logs.
        log.info("request", method=request.method, path=request.url.path, status=response.status_code,
                 ms=round((time.perf_counter() - start) * 1000, 1), request_id=request_id)
        return response

    app.include_router(health.router)
    for router in (auth.router, me.router, market.router, signals.router):
        app.include_router(router, prefix="/v1")
    return app


app = create_app()

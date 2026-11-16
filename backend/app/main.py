"""FastAPI application factory. ``app`` is the ASGI entry point (uvicorn app.main:app)."""

from __future__ import annotations

import hmac
import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, MutableMapping, Sequence
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

from app.api import health
from app.api.v1 import (
    admin,
    alerts,
    auth,
    dev_auth,
    journal,
    live,
    market,
    me,
    news,
    plans,
    radar,
    risk,
    signals,
    stream,
    tools,
    watchlists,
)
from app.core.config import Settings, get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging, get_logger
from app.core.observability import HTTP_LATENCY, HTTP_REQUESTS, init_sentry, metrics_payload
from app.core.ratelimit import RateLimiter
from app.db.session import make_engine, make_sessionmaker
from app.services.auth.google import GoogleTokenVerifier, http_jwks_fetcher
from app.services.marketdata.live import LiveCandles

VERSION = "0.5.0"
DESCRIPTION = """Zentrix: trading analysis and risk tools for FX, metals, commodities and crypto.

**Not financial advice.** Signals are probabilities based on past data, not guarantees. Accuracy figures come
only from the out-of-sample track record.

**Premium** features are marked "(Premium)" and with `x-premium` on the operation. Billing is not integrated: while
`PREMIUM_ENFORCED=false` (the default) every feature is unlocked for everyone. See `GET /v1/plans`."""

log = get_logger("app")
REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{8,64}")


def _routes(routes: Sequence[Any], prefix: str) -> Iterator[tuple[str, Any]]:
    """(full path template, endpoint) of every route, through included routers whether flattened or kept."""
    for r in routes:
        endpoint = getattr(r, "endpoint", None)
        if endpoint is not None and hasattr(r, "path"):
            yield prefix + r.path, endpoint
        elif hasattr(r, "original_router"):  # FastAPI >= 0.16x keeps included routers
            yield from _routes(r.original_router.routes, prefix + r.include_context.prefix)


def create_app(settings: Settings | None = None, *, redis: Redis | None = None,
               google_verifier: GoogleTokenVerifier | None = None,
               clock: Callable[[], float] = time.time) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(json=settings.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = make_engine(settings.database_url)
        app.state.settings = settings
        app.state.clock = clock
        app.state.engine = engine
        app.state.sessionmaker = make_sessionmaker(engine)
        # Short timeouts: if Redis is down, rate limiting fails open fast instead of stalling every request.
        app.state.redis = redis or Redis.from_url(settings.redis_url, socket_connect_timeout=0.25, socket_timeout=0.5)
        app.state.rate_limiter = RateLimiter(app.state.redis)
        app.state.google_verifier = google_verifier or GoogleTokenVerifier(
            settings.google_client_ids, http_jwks_fetcher(settings.google_jwks_url))
        app.state.live_candles = LiveCandles(settings.live_candle_cache_s, clock)
        try:
            yield
        finally:
            await app.state.live_candles.aclose()
            await engine.dispose()
            if redis is None:
                await app.state.redis.aclose()

    init_sentry(settings, "api", f"zentrix-api@{VERSION}")
    docs = settings.docs_on
    app = FastAPI(title="Zentrix API", version=VERSION, description=DESCRIPTION, lifespan=lifespan,
                  docs_url="/docs" if docs else None, redoc_url="/redoc" if docs else None,
                  openapi_url="/openapi.json" if docs else None,
                  openapi_tags=[{"name": "auth", "description": "Google sign-in and sessions"},
                                {"name": "account", "description": "Profile, preferences, account deletion"},
                                {"name": "market", "description": "Instruments, venues, timeframes, candles"},
                                {"name": "signals", "description": "Live signals, outcomes, track record, models"},
                                {"name": "news", "description": "Economic calendar and news guard"},
                                {"name": "tools", "description": "Conditions, ATR levels, exit advice, scenario"},
                                {"name": "risk", "description": "Position size, risk profile, daily risk status"},
                                {"name": "journal", "description": "Trade journal, statistics, review"},
                                {"name": "watchlists", "description": "Watchlists and quotes"},
                                {"name": "alerts", "description": "Devices (FCM), alerts, alert inbox"},
                                {"name": "plans", "description": "Free and Premium features (no billing yet)"},
                                {"name": "admin", "description": "Admins: user plans and entitlement grants"},
                                {"name": "ops", "description": "Health checks"}])
    install_error_handlers(app)
    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"],
                           allow_headers=["Authorization", "Content-Type"])

    @app.middleware("http")
    async def request_context(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        # A client's X-Request-ID is reused only if it is a plain token (no log injection).
        given = request.headers.get("x-request-id", "")
        request_id = given if REQUEST_ID.fullmatch(given) else uuid.uuid4().hex
        request.state.request_id = request_id
        length = request.headers.get("content-length")
        if length is not None and (not length.isdigit() or int(length) > settings.max_body_bytes):
            too_big = length.isdigit()
            return JSONResponse(
                {"error": {"code": "payload_too_large" if too_big else "bad_request",
                           "message": "Request body too large" if too_big else "Invalid Content-Length"}},
                status_code=413 if too_big else 400, headers={"X-Request-ID": request_id})
        structlog.contextvars.bind_contextvars(request_id=request_id)
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
        finally:
            structlog.contextvars.clear_contextvars()
            elapsed = time.perf_counter() - start
            route = _route_label(request.scope)
            HTTP_REQUESTS.labels(request.method, route, str(status)).inc()
            HTTP_LATENCY.labels(request.method, route).observe(elapsed)
        _harden(request, response)
        response.headers["X-Request-ID"] = request_id
        # Path only (no query string, headers or bodies): tokens never reach the logs.
        log.info("request", method=request.method, path=request.url.path, status=status,
                 ms=round(elapsed * 1000, 1), request_id=request_id)
        return response

    endpoint_paths: dict[Any, str] = {}

    def _route_label(scope: MutableMapping[str, Any]) -> str:
        """Path template of the matched route (low-cardinality metric label), e.g. /v1/candles/live."""
        if not endpoint_paths:
            for path, endpoint in _routes(app.routes, ""):
                endpoint_paths.setdefault(endpoint, path)
        return endpoint_paths.get(scope.get("endpoint"), "unmatched")

    def _harden(request: Request, response: Response) -> None:
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "no-referrer")
        if not request.url.path.startswith(("/docs", "/redoc")):
            h.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        if request.headers.get("authorization"):
            h["Cache-Control"] = "no-store"  # personal data must not sit in shared or browser caches
        if settings.is_deployed:
            h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")

    async def metrics(request: Request) -> Response:
        """Prometheus scrape target (a plain route: not part of the public API or its OpenAPI spec)."""
        token = settings.metrics_token.get_secret_value()
        if token:
            sent = request.headers.get("authorization", "")
            if not hmac.compare_digest(sent.encode(), f"Bearer {token}".encode()):
                return JSONResponse({"error": {"code": "unauthorized", "message": "Metrics token required"}},
                                    status_code=401)
        elif settings.is_deployed:  # never public outside dev without a token
            return JSONResponse({"error": {"code": "not_found", "message": "Not Found"}}, status_code=404)
        body, content_type = metrics_payload()
        return Response(body, media_type=content_type)

    app.add_route("/metrics", metrics, methods=["GET"], include_in_schema=False)

    app.include_router(health.router)
    for router in (auth.router, me.router, market.router, live.router, signals.router, news.router, tools.router,
                   radar.router,
                   risk.router, journal.router, watchlists.router, alerts.router, stream.router, plans.router,
                   admin.router):
        app.include_router(router, prefix="/v1")
    if settings.dev_login and settings.app_env in ("dev", "test"):
        app.include_router(dev_auth.router, prefix="/v1")  # developer sign-in, never in staging/prod
        log.warning("dev_login_enabled")
    return app


app = create_app()

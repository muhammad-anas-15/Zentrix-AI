"""Error tracking (Sentry, optional) and Prometheus metrics.

Sentry stays off until ``SENTRY_DSN`` is set. Events never carry personal data: ``send_default_pii`` is off and
``scrub`` removes auth headers, cookies, query strings and client addresses before an event leaves the process.

Metrics use the Prometheus text format. With several uvicorn workers set ``PROMETHEUS_MULTIPROC_DIR`` to an empty,
writable directory so ``/metrics`` aggregates every worker (prometheus-client multiprocess mode).
"""

from __future__ import annotations

import os
from typing import Any

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    multiprocess,
)

from app.core.config import Settings
from app.core.logging import get_logger

log = get_logger(__name__)
SENSITIVE_HEADERS = {"authorization", "cookie", "set-cookie", "x-api-key", "proxy-authorization"}

HTTP_REQUESTS = Counter("zentrix_http_requests_total", "HTTP requests", ["method", "route", "status"])
HTTP_LATENCY = Histogram("zentrix_http_request_duration_seconds", "HTTP request duration", ["method", "route"],
                         buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30))

WORKER_TICKS = Counter("zentrix_worker_ticks_total", "Worker ticks")
WORKER_TICK_SECONDS = Histogram("zentrix_worker_tick_duration_seconds", "Worker tick duration",
                                buckets=(0.1, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300))
WORKER_CANDLES = Counter("zentrix_worker_candles_ingested_total", "Candles stored (fetched or built)")
WORKER_SIGNALS = Counter("zentrix_worker_signals_total", "Signals created")
WORKER_ERRORS = Counter("zentrix_worker_errors_total", "Errors in a tick (feed, calendar, headlines, alerts)")
WORKER_LAST_TICK = Gauge("zentrix_worker_last_tick_timestamp_seconds", "Unix time of the last finished tick")


def scrub(event: dict[str, Any], _hint: dict[str, Any] | None = None) -> dict[str, Any]:
    """Remove personal and secret data from a Sentry event."""
    req = event.get("request")
    if isinstance(req, dict):
        headers = req.get("headers")
        if isinstance(headers, dict):
            req["headers"] = {k: ("[removed]" if k.lower() in SENSITIVE_HEADERS else v) for k, v in headers.items()}
        for key in ("cookies", "query_string", "data", "env"):
            req.pop(key, None)
    event.pop("user", None)
    return event


def init_sentry(settings: Settings, component: str, release: str) -> bool:
    """Start Sentry for this process when SENTRY_DSN is set. Returns whether it is on."""
    dsn = settings.sentry_dsn.get_secret_value()
    if not dsn:
        return False
    import sentry_sdk

    sentry_sdk.init(dsn=dsn, environment=settings.app_env, release=release, send_default_pii=False,
                    traces_sample_rate=settings.sentry_traces_sample_rate, before_send=scrub,  # type: ignore[arg-type]
                    max_request_body_size="never")
    sentry_sdk.set_tag("component", component)
    log.info("sentry_enabled", component=component)
    return True


def metrics_payload() -> tuple[bytes, str]:
    """Current metrics (all uvicorn workers when PROMETHEUS_MULTIPROC_DIR is set)."""
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return generate_latest(registry), CONTENT_TYPE_LATEST
    return generate_latest(), CONTENT_TYPE_LATEST

"""Worker process: ingest candles, generate signals at each candle close, resolve outcomes, refresh the
economic calendar, evaluate alerts and send push notifications.

Run (from backend/):  python -m app.workers.main
Register trained models first: python -m app.workers.register_models
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import socket
import time
import uuid

from prometheus_client import start_http_server
from redis.asyncio import Redis

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.core.observability import (
    WORKER_CANDLES,
    WORKER_ERRORS,
    WORKER_LAST_TICK,
    WORKER_SIGNALS,
    WORKER_TICK_SECONDS,
    WORKER_TICKS,
    init_sentry,
)
from app.db.session import make_engine, make_sessionmaker
from app.services.alerts.push import make_sender
from app.services.marketdata.providers import default_providers
from app.services.news.calendar import HttpCalendarSource
from app.services.news.headlines import HttpHeadlineSource
from app.services.signals.registry import PredictorCache
from app.workers.ingest import TickReport, Worker

log = get_logger("worker")
LOCK_KEY = "lock:worker:tick"


def record_tick(report: TickReport, seconds: float) -> None:
    WORKER_TICKS.inc()
    WORKER_TICK_SECONDS.observe(seconds)
    WORKER_CANDLES.inc(sum(report.ingested.values()))
    WORKER_SIGNALS.inc(len(report.signals))
    WORKER_ERRORS.inc(len(report.errors))
    WORKER_LAST_TICK.set(time.time())


async def run(settings: Settings, stop: asyncio.Event) -> None:
    engine = make_engine(settings.database_url)
    redis = Redis.from_url(settings.redis_url, socket_connect_timeout=0.25, socket_timeout=2)
    worker = Worker(make_sessionmaker(engine), redis, default_providers(), PredictorCache(settings.artifacts_dir),
                    settings, calendar=HttpCalendarSource(settings.news_calendar_urls),
                    push=make_sender(settings.fcm_credentials_file), headlines=HttpHeadlineSource())
    me = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
    log.info("worker_started", id=me)
    try:
        while not stop.is_set():
            try:
                # One tick at a time across all workers (ticks are idempotent; the lock avoids wasted API calls).
                got = await redis.set(LOCK_KEY, me, nx=True, px=10 * 60 * 1000)
            except Exception:
                got = True  # Redis down: run anyway (single-worker deployments)
            if got:
                started = time.perf_counter()
                try:
                    report = await worker.tick()
                    record_tick(report, time.perf_counter() - started)
                except Exception:
                    WORKER_ERRORS.inc()
                    log.exception("tick_failed")
                finally:
                    try:
                        if await redis.get(LOCK_KEY) == me.encode():
                            await redis.delete(LOCK_KEY)
                    except Exception:
                        pass
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=settings.worker_poll_s)
    finally:
        await engine.dispose()
        await redis.aclose()
        log.info("worker_stopped")


def main() -> None:
    settings = get_settings()
    configure_logging(json=settings.log_json)
    init_sentry(settings, "worker", "zentrix-worker@0.6.0")
    if settings.worker_metrics_port:
        start_http_server(settings.worker_metrics_port)  # Prometheus scrape target; keep the port private
        log.info("worker_metrics", port=settings.worker_metrics_port)
    stop = asyncio.Event()

    async def _main() -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop.set)
            except NotImplementedError:  # Windows
                signal.signal(sig, lambda *_: stop.set())
        await run(settings, stop)

    asyncio.run(_main())


if __name__ == "__main__":
    main()

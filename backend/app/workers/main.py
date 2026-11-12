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
import uuid

from redis.asyncio import Redis

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import make_engine, make_sessionmaker
from app.services.marketdata.providers import default_providers
from app.services.news.calendar import HttpCalendarSource
from app.services.signals.registry import PredictorCache
from app.workers.ingest import Worker

log = get_logger("worker")
LOCK_KEY = "lock:worker:tick"


async def run(settings: Settings, stop: asyncio.Event) -> None:
    engine = make_engine(settings.database_url)
    redis = Redis.from_url(settings.redis_url, socket_connect_timeout=0.25, socket_timeout=2)
    worker = Worker(make_sessionmaker(engine), redis, default_providers(), PredictorCache(settings.artifacts_dir),
                    settings, calendar=HttpCalendarSource(settings.news_calendar_urls))
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
                try:
                    await worker.tick()
                except Exception:
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

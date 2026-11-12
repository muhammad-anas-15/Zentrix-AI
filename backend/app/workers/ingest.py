"""Ingestion worker core: one ``tick(now)`` ingests every due series, then runs the signal job, the outcome
resolver and the price/signal alert evaluation for the series that received new candles. Each tick also refreshes
the economic calendar (hourly), evaluates news alerts and delivers pending push notifications.

A series is due when a candle should have closed since its last stored candle (after ``ingest_grace_s``),
the market was open for that slot, and it was not attempted in the last ``ingest_retry_s``. Venues are fetched
concurrently, series within a venue sequentially (provider rate limits). Only closed, market-hours candles are
stored. Jobs are idempotent (upserts, unique signal per model + candle), so re-running a tick is safe.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pandas as pd
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.market import Instrument, InstrumentListing, Venue
from app.models.signals import IngestionTarget
from app.services.alerts import evaluator
from app.services.alerts.push import DisabledSender, PushSender, deliver_pending
from app.services.marketdata.candles import last_candle_times, upsert_candles
from app.services.marketdata.providers import Provider
from app.services.news.calendar import CalendarSource, refresh_calendar
from app.services.realtime import candle_event, publish
from app.services.signals.cache import bump_track_record_version, cache_latest_signals
from app.services.signals.engine import generate_signals
from app.services.signals.outcomes import resolve_series
from app.services.signals.registry import PredictorCache
from ml.data.candles import drop_unclosed, interval_seconds
from ml.data.sessions import is_market_open, trading_hours_only

log = get_logger(__name__)
Series = tuple[int, str]  # (listing_id, timeframe)


@dataclass(frozen=True)
class Target:
    listing_id: int
    instrument_id: int
    symbol: str
    timeframe: str
    venue: str
    venue_symbol: str
    session: str
    priority: int
    backfill: int

    @property
    def series(self) -> Series:
        return (self.listing_id, self.timeframe)

    @property
    def tf_s(self) -> int:
        return interval_seconds(self.timeframe)


@dataclass
class TickReport:
    ingested: dict[Series, int] = field(default_factory=dict)
    signals: list[int] = field(default_factory=list)
    outcomes: int = 0
    alerts: list[int] = field(default_factory=list)
    pushes: dict[str, int] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Ingested:
    prev_last: int | None  # newest stored open time before this ingest (None: first time this series is seen)
    candles: pd.DataFrame


class Worker:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], redis: Redis,
                 providers: dict[str, Provider], predictors: PredictorCache, settings: Settings,
                 clock: Callable[[], float] = time.time, calendar: CalendarSource | None = None,
                 push: PushSender | None = None) -> None:
        self.sessionmaker = sessionmaker
        self.redis = redis
        self.providers = providers
        self.predictors = predictors
        self.settings = settings
        self.clock = clock  # wall clock; signals are stamped and lag-checked with it at the moment they are made
        self.calendar = calendar
        self.push = push or DisabledSender()
        self._last_ts: dict[Series, int] | None = None
        self._last_attempt: dict[Series, float] = {}
        self._calendar_next = 0.0

    async def load_targets(self, db: AsyncSession) -> list[Target]:
        rows = (await db.execute(
            select(IngestionTarget, InstrumentListing, Venue.code, Instrument.session, Instrument.id,
                   Instrument.symbol)
            .join(InstrumentListing, InstrumentListing.id == IngestionTarget.listing_id)
            .join(Venue, Venue.id == InstrumentListing.venue_id)
            .join(Instrument, Instrument.id == InstrumentListing.instrument_id)
            .where(IngestionTarget.enabled, InstrumentListing.status == "active", Venue.active)
            .order_by(IngestionTarget.priority, IngestionTarget.id))).all()
        return [Target(t.listing_id, iid, sym, t.timeframe, venue, li.venue_symbol, session, t.priority,
                       t.backfill_candles) for t, li, venue, session, iid, sym in rows]

    def latest_closed_open(self, t: Target, now: float) -> int:
        """Open time of the newest candle that should have closed by ``now - grace``."""
        return int((now - self.settings.ingest_grace_s) // t.tf_s * t.tf_s) - t.tf_s

    def is_due(self, t: Target, now: float) -> bool:
        assert self._last_ts is not None
        last = self._last_ts.get(t.series)
        attempted = self._last_attempt.get(t.series)
        if attempted is not None and now - attempted < self.settings.ingest_retry_s:
            return False
        if last is None:
            return True
        expected = self.latest_closed_open(t, now)
        return last < expected and is_market_open(expected, t.session)

    async def tick(self, now: float | None = None) -> TickReport:
        """``now`` decides which series are due; signal timing always uses ``self.clock()``."""
        now = self.clock() if now is None else now
        report = TickReport()
        async with self.sessionmaker() as db:
            if self._last_ts is None:
                self._last_ts = await last_candle_times(db)
            targets = await self.load_targets(db)
        by_venue: dict[str, list[Target]] = defaultdict(list)
        for t in targets:
            if t.venue in self.providers and self.is_due(t, now):
                by_venue[t.venue].append(t)
        # Venues run concurrently, so a slow, throttled venue never delays another venue's signals.
        await asyncio.gather(*(self._run_venue(venue, ts, now, report) for venue, ts in by_venue.items()))
        await self._refresh_calendar(now, report)
        await self._news_alerts_and_push(report)
        if report.signals or report.outcomes:
            await bump_track_record_version(self.redis)
        if report.ingested or report.signals or report.outcomes or report.errors:
            log.info("tick", ingested=sum(report.ingested.values()), series=len(report.ingested),
                     signals=len(report.signals), outcomes=report.outcomes, alerts=len(report.alerts),
                     errors=len(report.errors))
        return report

    async def _run_venue(self, venue: str, targets: list[Target], now: float, report: TickReport) -> None:
        """Higher timeframes first (their fresh candles feed the base series' trend feature), then each series
        is signalled and resolved right after it is ingested, keeping the signal lag minimal."""
        failed: set[Series] = set()
        for t in sorted(targets, key=lambda t: (-t.tf_s, t.priority)):
            got = await self._ingest(venue, t, now, report, failed)
            if got is not None:
                await self._process_series(t, failed, report, got)

    async def _ingest(self, venue: str, t: Target, now: float, report: TickReport,
                      failed: set[Series]) -> Ingested | None:
        """Fetch and store closed candles; returns them if the series has a new latest candle."""
        provider = self.providers[venue]
        if t.timeframe not in provider.timeframes:
            report.skipped.append(f"{venue} has no {t.timeframe}")
            return None
        self._last_attempt[t.series] = now
        if not await self._budget_ok(venue, now):
            report.skipped.append(f"{venue} daily budget exhausted")
            failed.add(t.series)
            return None
        assert self._last_ts is not None
        last = self._last_ts.get(t.series)
        gap = (self.latest_closed_open(t, now) - last) // t.tf_s if last is not None else t.backfill
        limit = int(min(max(gap + 3, 3), t.backfill))
        try:
            raw = await provider.fetch_latest(t.venue_symbol, t.timeframe, limit)
        except Exception as exc:
            failed.add(t.series)
            report.errors.append(f"{venue}:{t.venue_symbol}:{t.timeframe}: {type(exc).__name__}")
            log.warning("ingest_failed", venue=venue, symbol=t.venue_symbol, tf=t.timeframe, error=type(exc).__name__)
            return None
        candles = trading_hours_only(drop_unclosed(raw, t.timeframe, self.clock()), t.session)
        if candles.empty:
            return None
        async with self.sessionmaker() as db:
            n = await upsert_candles(db, t.listing_id, t.timeframe, candles)
            await db.commit()
        report.ingested[t.series] = n
        newest = int(candles["time"].max())
        if last is not None and newest <= last:
            return None
        self._last_ts[t.series] = newest
        await publish(self.redis, candle_event(t.symbol, t.venue, t.timeframe, candles.iloc[-1]))
        return Ingested(last, candles)

    async def _process_series(self, t: Target, failed: set[Series], report: TickReport, got: Ingested) -> None:
        assert self._last_ts is not None
        # a higher timeframe of this listing that failed to update this round must not feed features
        stale = frozenset(tf for (lid, tf) in failed if lid == t.listing_id)
        async with self.sessionmaker() as db:
            result = await generate_signals(
                db, self.predictors, t.listing_id, t.instrument_id, t.timeframe, self._last_ts[t.series],
                self.clock(), self.settings.signal_max_lag_s, stale_htf=stale)
            await db.commit()
            report.signals += result.created
            report.skipped += result.skipped
            report.outcomes += await resolve_series(db, t.listing_id, t.timeframe, self.clock(),
                                                    self.settings.outcome_void_after_s)
            await db.commit()
            now_dt = datetime.fromtimestamp(self.clock(), tz=UTC)
            if result.created:
                for sig in await cache_latest_signals(db, self.redis, result.created):
                    await publish(self.redis, {"type": "signal", **sig})
                report.alerts += await evaluator.on_signals(
                    db, result.created, now_dt, premium_enforced=self.settings.premium_enforced,
                    free_markets=(self.settings.free_signal_symbols, self.settings.free_signal_timeframes))
            if got.prev_last is not None:  # never alert on a first backfill
                report.alerts += await evaluator.on_candles(db, t.instrument_id, t.listing_id, t.timeframe,
                                                            got.prev_last, now_dt)
            await db.commit()

    async def _news_alerts_and_push(self, report: TickReport) -> None:
        now_dt = datetime.fromtimestamp(self.clock(), tz=UTC)
        try:
            async with self.sessionmaker() as db:
                report.alerts += await evaluator.news_tick(db, now_dt)
                await db.commit()
                report.pushes = await deliver_pending(db, self.push, now_dt, self.settings.push_max_attempts)
                await db.commit()
        except Exception as exc:
            report.errors.append(f"alerts: {type(exc).__name__}")
            log.exception("alerts_failed")

    async def _refresh_calendar(self, now: float, report: TickReport) -> None:
        """Economic calendar every ``news_refresh_s``; after a failure retry in 5 minutes."""
        if self.calendar is None or now < self._calendar_next:
            return
        try:
            async with self.sessionmaker() as db:
                await refresh_calendar(db, self.calendar)
            self._calendar_next = now + self.settings.news_refresh_s
        except Exception as exc:
            self._calendar_next = now + 300
            report.errors.append(f"calendar: {type(exc).__name__}")
            log.warning("calendar_refresh_failed", error=type(exc).__name__)

    async def _budget_ok(self, venue: str, now: float) -> bool:
        if venue != "twelvedata":
            return True
        key = f"budget:{venue}:{datetime.fromtimestamp(now, tz=UTC):%Y%m%d}"
        try:
            used = await self.redis.incr(key)
            await self.redis.expire(key, 2 * 86400)
        except Exception:
            return True  # Redis down: rely on the provider's own limits
        return int(used) <= self.settings.twelve_data_daily_budget

"""Ingestion worker core: one ``tick(now)`` ingests every due series, then runs the signal job and the outcome
resolver for the series that received new candles.

A series is due when a candle should have closed since its last stored candle (after ``ingest_grace_s``),
the market was open for that slot, and it was not attempted in the last ``ingest_retry_s``. Venues are fetched
concurrently, series within a venue sequentially (provider rate limits). Only closed, market-hours candles are
stored. Jobs are idempotent (upserts, unique signal per model + candle), so re-running a tick is safe.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.market import Instrument, InstrumentListing, Venue
from app.models.signals import IngestionTarget
from app.services.marketdata.candles import last_candle_times, upsert_candles
from app.services.marketdata.providers import Provider
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
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class Worker:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], redis: Redis,
                 providers: dict[str, Provider], predictors: PredictorCache, settings: Settings) -> None:
        self.sessionmaker = sessionmaker
        self.redis = redis
        self.providers = providers
        self.predictors = predictors
        self.settings = settings
        self._last_ts: dict[Series, int] | None = None
        self._last_attempt: dict[Series, float] = {}

    async def load_targets(self, db: AsyncSession) -> list[Target]:
        rows = (await db.execute(
            select(IngestionTarget, InstrumentListing, Venue.code, Instrument.session, Instrument.id)
            .join(InstrumentListing, InstrumentListing.id == IngestionTarget.listing_id)
            .join(Venue, Venue.id == InstrumentListing.venue_id)
            .join(Instrument, Instrument.id == InstrumentListing.instrument_id)
            .where(IngestionTarget.enabled, InstrumentListing.status == "active", Venue.active)
            .order_by(IngestionTarget.priority, IngestionTarget.id))).all()
        return [Target(t.listing_id, iid, t.timeframe, venue, li.venue_symbol, session, t.priority, t.backfill_candles)
                for t, li, venue, session, iid in rows]

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
        now = time.time() if now is None else now
        report = TickReport()
        async with self.sessionmaker() as db:
            if self._last_ts is None:
                self._last_ts = await last_candle_times(db)
            targets = await self.load_targets(db)
        due = [t for t in targets if t.venue in self.providers and self.is_due(t, now)]
        by_venue: dict[str, list[Target]] = defaultdict(list)
        for t in due:
            by_venue[t.venue].append(t)
        failed: set[Series] = set()
        new_latest: dict[Series, Target] = {}
        await asyncio.gather(*(self._ingest_venue(venue, ts, now, report, failed, new_latest)
                               for venue, ts in by_venue.items()))

        async with self.sessionmaker() as db:
            assert self._last_ts is not None
            for series, t in new_latest.items():
                # a higher timeframe of this listing that failed to update this round must not feed features
                stale = frozenset(tf for (lid, tf) in failed if lid == t.listing_id)
                result = await generate_signals(
                    db, self.predictors, t.listing_id, t.instrument_id, t.timeframe, self._last_ts[series], now,
                    self.settings.signal_max_lag_s, stale_htf=stale)
                report.signals += result.created
                report.skipped += result.skipped
            await db.commit()
            for series in new_latest:
                report.outcomes += await resolve_series(db, series[0], series[1], now,
                                                        self.settings.outcome_void_after_s)
            await db.commit()
            if report.signals:
                await cache_latest_signals(db, self.redis, report.signals)
        if report.signals or report.outcomes:
            await bump_track_record_version(self.redis)
        if report.ingested or report.signals or report.outcomes or report.errors:
            log.info("tick", ingested=sum(report.ingested.values()), series=len(report.ingested),
                     signals=len(report.signals), outcomes=report.outcomes, errors=len(report.errors))
        return report

    async def _ingest_venue(self, venue: str, targets: list[Target], now: float, report: TickReport,
                            failed: set[Series], new_latest: dict[Series, Target]) -> None:
        provider = self.providers[venue]
        for t in targets:
            if t.timeframe not in provider.timeframes:
                report.skipped.append(f"{venue} has no {t.timeframe}")
                continue
            self._last_attempt[t.series] = now
            if not await self._budget_ok(venue, now):
                report.skipped.append(f"{venue} daily budget exhausted")
                failed.add(t.series)
                continue
            assert self._last_ts is not None
            last = self._last_ts.get(t.series)
            gap = (self.latest_closed_open(t, now) - last) // t.tf_s if last is not None else t.backfill
            limit = int(min(max(gap + 3, 3), t.backfill))
            try:
                raw = await provider.fetch_latest(t.venue_symbol, t.timeframe, limit)
            except Exception as exc:
                failed.add(t.series)
                report.errors.append(f"{venue}:{t.venue_symbol}:{t.timeframe}: {type(exc).__name__}")
                log.warning("ingest_failed", venue=venue, symbol=t.venue_symbol, tf=t.timeframe,
                            error=type(exc).__name__)
                continue
            candles = trading_hours_only(drop_unclosed(raw, t.timeframe, now), t.session)
            if candles.empty:
                continue
            async with self.sessionmaker() as db:
                n = await upsert_candles(db, t.listing_id, t.timeframe, candles)
                await db.commit()
            report.ingested[t.series] = n
            newest = int(candles["time"].max())
            if last is None or newest > last:
                self._last_ts[t.series] = newest
                new_latest[t.series] = t

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

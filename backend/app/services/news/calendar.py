"""Economic calendar ingestion into ``news_events``.

Source: the ForexFactory weekly JSON (``nfs.faireconomy.media``). It is unofficial, has no published terms or
SLA and must be replaced by a licensed calendar before launch (docs/DATA_SOURCES.md). It is fetched hourly; the
publisher blocks clients that poll much faster. Next week's file only exists late in the week (404 before).

Each fetched file covers one calendar week (Sunday 00:00 to Sunday 00:00 New York time) and is authoritative for
it: events of that week that disappeared from the file (rescheduled or cancelled) are deleted, so a moved event
never lingers at its old time.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.tools import NewsEvent

log = get_logger(__name__)
SOURCE = "forexfactory"
DEFAULT_URLS = (
    "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
    "https://nfs.faireconomy.media/ff_calendar_nextweek.json",
)
NY = ZoneInfo("America/New_York")
IMPACTS = {"high": "high", "medium": "medium", "low": "low", "holiday": "holiday", "non-economic": "none"}


@dataclass(frozen=True)
class CalendarEvent:
    external_id: str
    title: str
    currency: str
    impact: str
    event_at: datetime
    forecast: str | None = None
    previous: str | None = None
    actual: str | None = None


def _text(v: Any, n: int) -> str | None:
    s = str(v).strip() if v is not None else ""
    return s[:n] or None


def parse_calendar(payload: Iterable[Mapping[str, Any]]) -> list[CalendarEvent]:
    """Feed rows -> events in UTC. Rows without a parseable timezone-aware date are skipped."""
    out: list[CalendarEvent] = []
    for row in payload:
        raw_date = str(row.get("date") or "")
        try:
            at = datetime.fromisoformat(raw_date)
        except ValueError:
            continue
        if at.tzinfo is None:
            continue
        title = (_text(row.get("title"), 200) or "Untitled event")
        currency = (_text(row.get("country"), 8) or "All").upper().replace("ALL", "All")
        impact = IMPACTS.get(str(row.get("impact") or "").strip().lower(), "none")
        digest = hashlib.sha1(f"{title}|{currency}|{raw_date}".encode()).hexdigest()
        out.append(CalendarEvent(digest, title, currency, impact, at.astimezone(UTC), _text(row.get("forecast"), 32),
                                 _text(row.get("previous"), 32), _text(row.get("actual"), 32)))
    return out


class CalendarSource(Protocol):
    async def fetch(self) -> list[list[CalendarEvent]]:
        """One batch per file; each batch is authoritative for its time window."""
        ...


class HttpCalendarSource:
    def __init__(self, urls: Iterable[str] = DEFAULT_URLS, timeout_s: float = 15.0,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.urls = list(urls)
        self.timeout_s = timeout_s
        self.transport = transport

    async def fetch(self) -> list[list[CalendarEvent]]:
        batches: list[list[CalendarEvent]] = []
        async with httpx.AsyncClient(timeout=self.timeout_s, transport=self.transport,
                                     headers={"User-Agent": "zentrix-calendar/1.0"}) as client:
            for url in self.urls:
                r = await client.get(url)
                if r.status_code == 404:  # next week's file is not published yet
                    continue
                r.raise_for_status()
                batches.append(parse_calendar(r.json()))
        return batches


def fetch_calendar_sync(urls: Iterable[str] = DEFAULT_URLS, timeout_s: float = 15.0) -> list[CalendarEvent]:
    """For the CLI assistant (no database). Failures return what was fetched so far."""
    events: list[CalendarEvent] = []
    with httpx.Client(timeout=timeout_s, headers={"User-Agent": "zentrix-calendar/1.0"}) as client:
        for url in urls:
            try:
                r = client.get(url)
                if r.status_code == 404:
                    continue
                r.raise_for_status()
                events += parse_calendar(r.json())
            except (httpx.HTTPError, ValueError) as exc:
                log.warning("calendar_fetch_failed", url=url, error=type(exc).__name__)
    return events


def week_window(at: datetime) -> tuple[datetime, datetime]:
    """The calendar week (Sunday 00:00 New York, 7 days) containing ``at``, in UTC."""
    local = at.astimezone(NY)
    sunday = (local - timedelta(days=(local.weekday() + 1) % 7)).replace(hour=0, minute=0, second=0, microsecond=0)
    start = datetime(sunday.year, sunday.month, sunday.day, tzinfo=NY)
    nxt = sunday + timedelta(days=7)
    return start.astimezone(UTC), datetime(nxt.year, nxt.month, nxt.day, tzinfo=NY).astimezone(UTC)


async def store_events(db: AsyncSession, batch: list[CalendarEvent], source: str = SOURCE) -> tuple[int, int]:
    """Upsert a batch (one weekly file) and delete events of this source in the weeks it covers that are no
    longer listed. Returns (upserted, removed). Caller commits."""
    if not batch:
        return 0, 0
    rows = [{"source": source, "external_id": e.external_id, "title": e.title, "currency": e.currency,
             "impact": e.impact, "event_at": e.event_at, "forecast": e.forecast, "previous": e.previous,
             "actual": e.actual} for e in batch]
    stmt = pg_insert(NewsEvent).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_news_events_source_external_id",
        set_={c: stmt.excluded[c] for c in ("title", "impact", "event_at", "forecast", "previous", "actual")}
        | {"fetched_at": datetime.now(UTC)})
    await db.execute(stmt)
    start = week_window(min(e.event_at for e in batch))[0]
    end = week_window(max(e.event_at for e in batch))[1]
    ids = {e.external_id for e in batch}
    stale = (await db.scalars(select(NewsEvent.id).where(
        NewsEvent.source == source, NewsEvent.event_at >= start, NewsEvent.event_at < end,
        NewsEvent.external_id.not_in(ids)))).all()
    if stale:
        await db.execute(delete(NewsEvent).where(NewsEvent.id.in_(stale)))
    return len(rows), len(stale)


async def refresh_calendar(db: AsyncSession, source: CalendarSource) -> tuple[int, int]:
    upserted = removed = 0
    for batch in await source.fetch():
        u, r = await store_events(db, batch)
        upserted, removed = upserted + u, removed + r
    await db.commit()
    log.info("calendar_refreshed", upserted=upserted, removed=removed)
    return upserted, removed

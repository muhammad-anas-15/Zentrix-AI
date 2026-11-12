"""Economic calendar and the per-instrument news guard. Public (IP rate limit)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.api.deps import DbDep, NowDep, SettingsDep
from app.core.ratelimit import limit_by_ip
from app.schemas.news import GuardOut, NewsEventOut, NewsEventsOut
from app.services.marketdata.lookup import instrument_by_symbol
from app.services.news.guard import GuardConfig, calendar_updated_at, guard_for, load_events

router = APIRouter(prefix="/news", tags=["news"], dependencies=[Depends(limit_by_ip("public", "rate_limit_public"))])
MIN_IMPACT = {"high": ("high",), "medium": ("high", "medium"), "low": ("high", "medium", "low")}


@router.get("/events", response_model=NewsEventsOut, summary="Economic calendar events")
async def news_events(
    db: DbDep, now: NowDep,
    currency: Annotated[str | None, Query(max_length=64, description="Comma-separated, e.g. USD,EUR")] = None,
    impact: Annotated[Literal["high", "medium", "low"], Query(description="Minimum impact")] = "medium",
    start: Annotated[datetime | None, Query(description="Default: 1 hour ago")] = None,
    end: Annotated[datetime | None, Query(description="Default: 7 days ahead")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> NewsEventsOut:
    currencies = frozenset(c.strip().upper() for c in currency.split(",") if c.strip()) if currency else None
    events = await load_events(db, currencies, start or now - timedelta(hours=1), end or now + timedelta(days=7),
                               MIN_IMPACT[impact], limit)
    return NewsEventsOut(items=[NewsEventOut(
        title=e.title, currency=e.currency, impact=e.impact, event_at=e.event_at,  # type: ignore[arg-type]
        in_s=int((e.event_at - now).total_seconds()), forecast=e.forecast, previous=e.previous, actual=e.actual)
        for e in events], calendar_updated_at=await calendar_updated_at(db))


@router.get("/guard", response_model=GuardOut, summary="News guard for an instrument: blackout / caution / clear")
async def news_guard(db: DbDep, now: NowDep, settings: SettingsDep,
                     symbol: Annotated[str, Query(min_length=3, max_length=40)]) -> GuardOut:
    inst = await instrument_by_symbol(db, symbol)
    g = await guard_for(db, inst.asset_class, inst.base, inst.quote, now, GuardConfig.from_settings(settings))
    return GuardOut(symbol=symbol, state=g.state, reasons=g.reasons,  # type: ignore[arg-type]
                    active_events=[NewsEventOut(**e) for e in g.active],
                    next_event=NewsEventOut(**g.next_event) if g.next_event else None, countdown_s=g.countdown_s,
                    blackout_until=g.blackout_until, currencies=g.currencies,
                    calendar_updated_at=g.calendar_updated_at)

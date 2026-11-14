"""Economic calendar, the per-instrument news guard and the Market Pulse headline feed. Public (IP rate limit)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, tuple_

from app.api.deps import DbDep, NowDep, SettingsDep
from app.core.ratelimit import limit_by_ip
from app.models.tools import NewsFeedStatus, NewsItem
from app.schemas.news import GuardOut, NewsEventOut, NewsEventsOut, NewsFeedOut, NewsItemOut, NewsSourceOut
from app.services.marketdata.lookup import instrument_by_symbol
from app.services.news.classify import METHOD, symbol_assets
from app.services.news.guard import GuardConfig, calendar_updated_at, guard_for, load_events
from app.services.news.headlines import FEEDS_BY_CODE, enabled_feeds

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


@router.get("/feed", response_model=NewsFeedOut, summary="Market Pulse: headlines with impact tags and asset badges")
async def news_feed(
    db: DbDep, now: NowDep, settings: SettingsDep,
    asset: Annotated[str | None, Query(max_length=120, description="Comma-separated, e.g. USD,BTC")] = None,
    symbol: Annotated[str | None, Query(min_length=3, max_length=40,
                                        description="Headlines reaching this instrument")] = None,
    impact: Annotated[Literal["high", "medium", "low"], Query(description="Minimum impact")] = "low",
    kind: Annotated[str | None, Query(max_length=60, description="central_bank,regulator,headline")] = None,
    q: Annotated[str | None, Query(max_length=60, description="Words in the headline")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 40,
    before_id: Annotated[int | None, Query(ge=1)] = None,
) -> NewsFeedOut:
    assets: set[str] = {a.strip().upper() for a in asset.split(",") if a.strip()} if asset else set()
    if symbol:
        inst = await instrument_by_symbol(db, symbol)
        assets |= symbol_assets(inst.asset_class, inst.base, inst.quote)
    feeds = enabled_feeds(settings.news_feeds)
    stmt = select(NewsItem).where(NewsItem.source.in_([f.code for f in feeds]),
                                  NewsItem.impact.in_(MIN_IMPACT[impact]))
    if assets:
        stmt = stmt.where(NewsItem.assets.overlap(sorted(assets)))
    if kind:
        stmt = stmt.where(NewsItem.kind.in_([k.strip() for k in kind.split(",") if k.strip()]))
    if q:
        stmt = stmt.where(NewsItem.title.ilike(f"%{q.replace('%', '').replace('_', ' ')}%"))
    if before_id:  # keyset on the sort order (published_at, id)
        pivot = select(NewsItem.published_at).where(NewsItem.id == before_id).scalar_subquery()
        stmt = stmt.where(tuple_(NewsItem.published_at, NewsItem.id) < tuple_(pivot, before_id))
    rows = (await db.scalars(stmt.order_by(NewsItem.published_at.desc(), NewsItem.id.desc())
                             .limit(limit + 1))).all()
    page = rows[:limit]
    status = {s.code: s for s in (await db.scalars(select(NewsFeedStatus))).all()}
    sources = [NewsSourceOut(code=f.code, name=f.name, kind=f.kind,  # type: ignore[arg-type]
                             ok=f.code in status and status[f.code].last_error is None,
                             last_ok_at=status[f.code].last_ok_at if f.code in status else None,
                             last_error=status[f.code].last_error if f.code in status else None) for f in feeds]
    oks = [s.last_ok_at for s in sources if s.last_ok_at is not None]
    return NewsFeedOut(
        items=[NewsItemOut(id=r.id, source=r.source, source_name=FEEDS_BY_CODE[r.source].name,
                           kind=r.kind, title=r.title, url=r.url, published_at=r.published_at,  # type: ignore[arg-type]
                           age_s=max(0, int((now - r.published_at).total_seconds())),
                           impact=r.impact, impact_reason=r.impact_reason, assets=list(r.assets))  # type: ignore[arg-type]
               for r in page],
        next_before_id=page[-1].id if len(rows) > limit else None, sources=sources,
        updated_at=max(oks) if oks else None, method=METHOD)


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

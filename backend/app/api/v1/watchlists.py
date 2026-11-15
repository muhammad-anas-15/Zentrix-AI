"""Watchlists (signed-in users): lists of instruments, ordering, and quotes per list."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Path, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbDep, NowDep, SettingsDep
from app.api.premium import GateDep, market_badge, partly_premium
from app.core.errors import AppError
from app.models.market import Instrument, InstrumentListing
from app.models.signals import Signal
from app.models.tools import Watchlist, WatchlistItem
from app.models.user import User
from app.schemas.alerts import (
    QuoteOut,
    QuoteSignalOut,
    QuotesOut,
    WatchlistIn,
    WatchlistItemIn,
    WatchlistItemOut,
    WatchlistItemsIn,
    WatchlistOut,
    WatchlistUpdate,
)
from app.services.entitlements import visible_signals
from app.services.marketdata.lookup import last_price
from app.services.news.guard import GuardConfig, calendar_updated_at, evaluate_guard, instrument_currencies, load_events

router = APIRouter(prefix="/watchlists", tags=["watchlists"])
ListId = Annotated[int, Path(ge=1)]


def wl_out(w: Watchlist) -> WatchlistOut:
    return WatchlistOut(id=w.id, name=w.name, sort_order=w.sort_order, created_at=w.created_at, items=[
        WatchlistItemOut(symbol=i.instrument.symbol, display_name=i.instrument.display_name,
                         asset_class=i.instrument.asset_class, sort_order=i.sort_order) for i in w.items])


async def own_list(db: AsyncSession, user: User, list_id: int) -> Watchlist:
    w = await db.get(Watchlist, list_id)
    if w is None or w.user_id != user.id:
        raise AppError(404, "not_found", f"No watchlist {list_id}")
    return w


async def instruments(db: AsyncSession, symbols: list[str]) -> list[Instrument]:
    ordered = list(dict.fromkeys(symbols))
    found = {i.symbol: i for i in (await db.scalars(select(Instrument).where(Instrument.symbol.in_(ordered)))).all()}
    missing = [s for s in ordered if s not in found]
    if missing:
        raise AppError(422, "unknown_instrument", f"Unknown symbols: {', '.join(missing)}", details=missing)
    return [found[s] for s in ordered]


async def _reload(db: AsyncSession, w: Watchlist) -> WatchlistOut:
    await db.commit()
    await db.refresh(w, attribute_names=["items"])
    return wl_out(w)


@router.get("", response_model=list[WatchlistOut], summary="Your watchlists")
async def list_watchlists(user: CurrentUser, db: DbDep) -> list[WatchlistOut]:
    rows = (await db.scalars(select(Watchlist).where(Watchlist.user_id == user.id)
                             .order_by(Watchlist.sort_order, Watchlist.id))).all()
    return [wl_out(w) for w in rows]


@router.post("", response_model=WatchlistOut, status_code=status.HTTP_201_CREATED, summary="Create a watchlist")
async def create_watchlist(body: WatchlistIn, user: CurrentUser, db: DbDep, settings: SettingsDep) -> WatchlistOut:
    count = await db.scalar(select(func.count()).select_from(Watchlist).where(Watchlist.user_id == user.id))
    if (count or 0) >= settings.max_watchlists_per_user:
        raise AppError(409, "limit_reached", f"At most {settings.max_watchlists_per_user} watchlists")
    if await db.scalar(select(Watchlist.id).where(Watchlist.user_id == user.id, Watchlist.name == body.name)):
        raise AppError(409, "name_taken", f"You already have a watchlist named {body.name!r}")
    w = Watchlist(user_id=user.id, name=body.name, sort_order=count or 0)
    w.items = [WatchlistItem(instrument_id=i.id, sort_order=n) for n, i in
               enumerate(await instruments(db, body.symbols))]
    db.add(w)
    return await _reload(db, w)


@router.patch("/{list_id}", response_model=WatchlistOut, summary="Rename or reorder a watchlist")
async def update_watchlist(body: WatchlistUpdate, user: CurrentUser, db: DbDep, list_id: ListId) -> WatchlistOut:
    w = await own_list(db, user, list_id)
    if body.name is not None and body.name != w.name:
        if await db.scalar(select(Watchlist.id).where(Watchlist.user_id == user.id, Watchlist.name == body.name)):
            raise AppError(409, "name_taken", f"You already have a watchlist named {body.name!r}")
        w.name = body.name
    if body.sort_order is not None:
        w.sort_order = body.sort_order
    return await _reload(db, w)


@router.delete("/{list_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a watchlist")
async def delete_watchlist(user: CurrentUser, db: DbDep, list_id: ListId) -> Response:
    await db.delete(await own_list(db, user, list_id))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{list_id}/items", response_model=WatchlistOut, summary="Replace the items (in this order)")
async def replace_items(body: WatchlistItemsIn, user: CurrentUser, db: DbDep, list_id: ListId) -> WatchlistOut:
    w = await own_list(db, user, list_id)
    insts = await instruments(db, body.symbols)
    by_inst = {i.instrument_id: i for i in w.items}
    keep = []
    for n, inst in enumerate(insts):
        item = by_inst.pop(inst.id, None) or WatchlistItem(instrument_id=inst.id)
        item.sort_order = n
        keep.append(item)
    w.items = keep
    return await _reload(db, w)


@router.post("/{list_id}/items", response_model=WatchlistOut, summary="Add an instrument at the end")
async def add_item(body: WatchlistItemIn, user: CurrentUser, db: DbDep, settings: SettingsDep,
                   list_id: ListId) -> WatchlistOut:
    w = await own_list(db, user, list_id)
    inst = (await instruments(db, [body.symbol]))[0]
    if all(i.instrument_id != inst.id for i in w.items):
        if len(w.items) >= settings.max_watchlist_items:
            raise AppError(409, "limit_reached", f"At most {settings.max_watchlist_items} items per watchlist")
        w.items.append(WatchlistItem(instrument_id=inst.id, sort_order=max((i.sort_order for i in w.items),
                                                                           default=-1) + 1))
    return await _reload(db, w)


@router.delete("/{list_id}/items", response_model=WatchlistOut, summary="Remove an instrument")
async def remove_item(user: CurrentUser, db: DbDep, list_id: ListId,
                      symbol: Annotated[str, Query(min_length=3, max_length=40)]) -> WatchlistOut:
    w = await own_list(db, user, list_id)
    w.items = [i for i in w.items if i.instrument.symbol != symbol]
    return await _reload(db, w)


@router.get("/{list_id}/quotes", response_model=QuotesOut,
            summary="Last closed price, 24h change, latest signal and news state per item",
            **partly_premium("all_markets"))
async def quotes(user: CurrentUser, db: DbDep, now: NowDep, settings: SettingsDep, gate: GateDep,
                 list_id: ListId) -> QuotesOut:
    w = await own_list(db, user, list_id)
    inst_ids = [i.instrument_id for i in w.items]
    listings = dict((await db.execute(select(InstrumentListing.instrument_id, InstrumentListing.id).where(
        InstrumentListing.instrument_id.in_(inst_ids), InstrumentListing.is_primary))).all())
    locked = gate.locked("all_markets")  # then: the latest signal each caller may see
    latest = {s.instrument_id: s for s in (await db.scalars(
        select(Signal).where(Signal.instrument_id.in_(inst_ids), *([visible_signals(settings)] if locked else []))
        .ext(distinct_on(Signal.instrument_id))
        .order_by(Signal.instrument_id, Signal.candle_ts.desc(), Signal.id.desc()))).unique().all()}
    cfg = GuardConfig.from_settings(settings)
    scopes = {i.instrument_id: instrument_currencies(i.instrument.asset_class, i.instrument.base,
                                                     i.instrument.quote) for i in w.items}
    all_cur = frozenset().union(*(c for c, _ in scopes.values())) if scopes else frozenset()
    events = await load_events(db, all_cur, now - timedelta(seconds=cfg.blackout_after_s), now + timedelta(days=8))
    updated = await calendar_updated_at(db)
    out = []
    for item in w.items:
        inst = item.instrument
        lid = listings.get(inst.id)
        lp = await last_price(db, lid) if lid else None
        prev = await last_price(db, lid, lp.as_of - timedelta(hours=24)) if lid and lp else None
        cur, high_only = scopes[inst.id]
        g = evaluate_guard(events, cur, high_only, now, cfg, updated)
        s = latest.get(inst.id)
        out.append(QuoteOut(
            symbol=inst.symbol, display_name=inst.display_name, price=lp.price if lp else None,
            as_of=lp.as_of if lp else None,
            change_24h_pct=(lp.price / prev.price - 1) * 100 if lp and prev else None,
            news_state=g.state, next_event=f"{g.next_event['currency']} {g.next_event['title']}" if g.next_event
            else None, next_event_in_s=g.countdown_s,
            latest_signal=QuoteSignalOut(id=s.id, timeframe=s.timeframe, horizon=s.horizon,
                                         direction=s.direction, strength=s.strength,  # type: ignore[arg-type]
                                         confidence=s.confidence, created_at=s.created_at,
                                         has_demonstrated_edge=s.model_usable,
                                         premium=market_badge(settings, inst.symbol, s.timeframe)) if s else None))
    return QuotesOut(watchlist_id=w.id, items=out, premium_locked=locked)

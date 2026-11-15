"""Public market reference data: instruments (all asset classes), venues, timeframes."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select

from app.api.deps import DbDep
from app.core.ratelimit import limit_by_ip
from app.models.market import Instrument, InstrumentListing, Timeframe, Venue
from app.models.signals import IngestionTarget
from app.schemas.market import InstrumentOut, InstrumentPage, ListingOut, TimeframeOut, VenueOut

router = APIRouter(tags=["market"], dependencies=[Depends(limit_by_ip("public", "rate_limit_public"))])


def _instrument_out(i: Instrument, timeframes: list[str] | None = None) -> InstrumentOut:
    return InstrumentOut(
        symbol=i.symbol, display_name=i.display_name, asset_class=i.asset_class,  # type: ignore[arg-type]
        instrument_type=i.instrument_type, base=i.base, quote=i.quote,  # type: ignore[arg-type]
        settle=i.settle, contract_size=i.contract_size, price_decimals=i.price_decimals, session=i.session,
        active=i.active,
        listings=[ListingOut(venue=li.venue.code, venue_symbol=li.venue_symbol, status=li.status,  # type: ignore[arg-type]
                             is_primary=li.is_primary, note=li.note) for li in i.listings],
        timeframes=timeframes or [],
    )


async def chart_timeframes(db: DbDep, instrument_ids: list[int]) -> dict[int, list[str]]:
    """Instrument id -> timeframes kept up to date on its primary listing, shortest first."""
    if not instrument_ids:
        return {}
    rows = (await db.execute(
        select(InstrumentListing.instrument_id, IngestionTarget.timeframe)
        .join(IngestionTarget, IngestionTarget.listing_id == InstrumentListing.id)
        .join(Timeframe, Timeframe.code == IngestionTarget.timeframe)
        .where(InstrumentListing.instrument_id.in_(instrument_ids), InstrumentListing.is_primary,
               IngestionTarget.enabled)
        .order_by(Timeframe.seconds))).all()
    out: dict[int, list[str]] = {}
    for iid, tf in rows:
        out.setdefault(iid, []).append(tf)
    return out


@router.get("/instruments", response_model=InstrumentPage, summary="List instruments across asset classes")
async def list_instruments(
    db: DbDep,
    asset_class: Annotated[Literal["fx", "metal", "commodity", "crypto", "index", "equity"] | None, Query()] = None,
    instrument_type: Annotated[Literal["spot", "perpetual", "future", "cfd"] | None, Query()] = None,
    venue: Annotated[str | None, Query(max_length=32, description="Venue code, e.g. binance_spot")] = None,
    q: Annotated[str | None, Query(max_length=40, description="Search symbol or name")] = None,
    include_inactive: Annotated[bool, Query(description="Also list instruments without a usable feed")] = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> InstrumentPage:
    stmt = select(Instrument)
    if not include_inactive:
        stmt = stmt.where(Instrument.active.is_(True))
    if asset_class:
        stmt = stmt.where(Instrument.asset_class == asset_class)
    if instrument_type:
        stmt = stmt.where(Instrument.instrument_type == instrument_type)
    if venue:
        stmt = stmt.where(Instrument.listings.any(InstrumentListing.venue.has(Venue.code == venue)))
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(or_(Instrument.symbol.ilike(pattern), Instrument.display_name.ilike(pattern)))
    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    page = stmt.order_by(Instrument.asset_class, Instrument.symbol).limit(limit).offset(offset)
    rows = (await db.scalars(page)).all()
    tfs = await chart_timeframes(db, [i.id for i in rows])
    return InstrumentPage(items=[_instrument_out(i, tfs.get(i.id)) for i in rows], total=total, limit=limit,
                          offset=offset)


@router.get("/timeframes", response_model=list[TimeframeOut], summary="Supported candle timeframes")
async def list_timeframes(db: DbDep) -> list[TimeframeOut]:
    rows = (await db.scalars(select(Timeframe).order_by(Timeframe.sort_order))).all()
    return [TimeframeOut.model_validate(r) for r in rows]


@router.get("/venues", response_model=list[VenueOut], summary="Exchanges and data vendors")
async def list_venues(db: DbDep) -> list[VenueOut]:
    rows = (await db.scalars(select(Venue).where(Venue.active.is_(True)).order_by(Venue.code))).all()
    return [VenueOut.model_validate(r) for r in rows]

"""Instrument / listing lookup by canonical symbol, and the freshest stored price of a listing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.market import Candle, Instrument, InstrumentListing, Timeframe, Venue
from ml.data.candles import interval_seconds


@dataclass(frozen=True)
class ListingRef:
    instrument: Instrument
    listing: InstrumentListing
    venue: str


async def instrument_by_symbol(db: AsyncSession, symbol: str) -> Instrument:
    inst = await db.scalar(select(Instrument).where(Instrument.symbol == symbol))
    if inst is None:
        raise AppError(404, "unknown_instrument", f"No instrument {symbol}")
    return inst


async def listing_for(db: AsyncSession, symbol: str, venue: str | None = None) -> ListingRef:
    """The instrument's listing on ``venue``, or its primary listing."""
    stmt = (select(Instrument, InstrumentListing, Venue.code)
            .join(InstrumentListing, InstrumentListing.instrument_id == Instrument.id)
            .join(Venue, Venue.id == InstrumentListing.venue_id).where(Instrument.symbol == symbol))
    stmt = stmt.where(Venue.code == venue) if venue else stmt.where(InstrumentListing.is_primary)
    row = (await db.execute(stmt)).first()
    if row is None:
        raise AppError(404, "unknown_instrument", f"No {'listing on ' + venue if venue else 'instrument'} for {symbol}")
    return ListingRef(row[0], row[1], row[2])


@dataclass(frozen=True)
class LastPrice:
    price: float
    candle_open: datetime
    timeframe: str

    @property
    def as_of(self) -> datetime:
        """Close time of the candle the price comes from."""
        return self.candle_open + timedelta(seconds=interval_seconds(self.timeframe))


async def last_price(db: AsyncSession, listing_id: int, at: datetime | None = None) -> LastPrice | None:
    """Close of the most recently *closed* stored candle over all timeframes (closing at/before ``at``)."""
    stmt = (select(Candle.timeframe, Candle.ts, Candle.close).where(Candle.listing_id == listing_id)
            .distinct(Candle.timeframe).order_by(Candle.timeframe, Candle.ts.desc()))
    if at is not None:
        stmt = stmt.join(Timeframe, Timeframe.code == Candle.timeframe).where(
            Candle.ts + func.make_interval(0, 0, 0, 0, 0, 0, Timeframe.seconds) <= at)
    best: LastPrice | None = None
    for tf, ts, close in (await db.execute(stmt)).all():
        p = LastPrice(close, ts, tf)
        if best is None or p.as_of > best.as_of:
            best = p
    return best

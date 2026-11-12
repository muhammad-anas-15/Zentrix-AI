"""Multi-asset, multi-venue market reference data and candles (see docs/ARCHITECTURE.md).

Instrument = what the user trades/analyses (EUR/USD, BTC/USDT, BTC/USDT:PERP). Listing = one venue's feed
for it. Candles reference a listing; user objects (watchlists, alerts, journal) reference an instrument.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

ASSET_CLASSES = ("fx", "metal", "commodity", "crypto", "index", "equity")
INSTRUMENT_TYPES = ("spot", "perpetual", "future", "cfd")
VENUE_KINDS = ("exchange", "data_vendor", "broker")
LISTING_STATUSES = ("active", "planned", "restricted", "disabled")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Venue(Base):
    __tablename__ = "venues"
    __table_args__ = (CheckConstraint(_in("kind", VENUE_KINDS), name="kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(16))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class Timeframe(Base):
    __tablename__ = "timeframes"

    code: Mapped[str] = mapped_column(String(8), primary_key=True)
    seconds: Mapped[int] = mapped_column(Integer)
    sort_order: Mapped[int] = mapped_column(SmallInteger)


class Instrument(Base):
    __tablename__ = "instruments"
    __table_args__ = (
        CheckConstraint(_in("asset_class", ASSET_CLASSES), name="asset_class"),
        CheckConstraint(_in("instrument_type", INSTRUMENT_TYPES), name="instrument_type"),
        Index("ix_instruments_asset_class_active", "asset_class", "active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(40), unique=True)  # canonical, venue-independent
    display_name: Mapped[str] = mapped_column(String(80))
    asset_class: Mapped[str] = mapped_column(String(16))
    instrument_type: Mapped[str] = mapped_column(String(16))
    base: Mapped[str] = mapped_column(String(16))
    quote: Mapped[str] = mapped_column(String(16))
    settle: Mapped[str | None] = mapped_column(String(16))  # margin/settlement asset for derivatives
    expiry: Mapped[datetime | None] = mapped_column(Date)  # dated futures only
    contract_size: Mapped[float | None] = mapped_column(Double)  # units per lot/contract
    price_decimals: Mapped[int] = mapped_column(SmallInteger)  # default display precision
    session: Mapped[str] = mapped_column(String(32))  # market-hours calendar code, see ml/data/sessions.py
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))

    listings: Mapped[list[InstrumentListing]] = relationship(back_populates="instrument", lazy="selectin",
                                                             order_by="InstrumentListing.id")


class InstrumentListing(Base):
    __tablename__ = "instrument_listings"
    __table_args__ = (
        UniqueConstraint("venue_id", "venue_symbol", name="uq_instrument_listings_venue_symbol"),
        CheckConstraint(_in("status", LISTING_STATUSES), name="status"),
        # at most one primary listing per instrument
        Index("uq_instrument_listings_primary", "instrument_id", unique=True,
              postgresql_where=text("is_primary")),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id", ondelete="CASCADE"), index=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id", ondelete="RESTRICT"), index=True)
    venue_symbol: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(16))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    note: Mapped[str | None] = mapped_column(Text)

    instrument: Mapped[Instrument] = relationship(back_populates="listings")
    venue: Mapped[Venue] = relationship(lazy="joined")


class Candle(Base):
    """Closed candles only. Range-partitioned by month on ``ts`` (open time, UTC); partitions are created by
    ``zx_ensure_candle_partitions(from, to)`` (migration 0002, then the ingestion worker)."""

    __tablename__ = "candles"
    __table_args__ = ({"postgresql_partition_by": "RANGE (ts)"},)

    listing_id: Mapped[int] = mapped_column(ForeignKey("instrument_listings.id", ondelete="CASCADE"),
                                            primary_key=True)
    timeframe: Mapped[str] = mapped_column(ForeignKey("timeframes.code"), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    open: Mapped[float] = mapped_column(Double)
    high: Mapped[float] = mapped_column(Double)
    low: Mapped[float] = mapped_column(Double)
    close: Mapped[float] = mapped_column(Double)
    volume: Mapped[float | None] = mapped_column(Double)
    quote_volume: Mapped[float | None] = mapped_column(Double)
    trades: Mapped[int | None] = mapped_column(BigInteger)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

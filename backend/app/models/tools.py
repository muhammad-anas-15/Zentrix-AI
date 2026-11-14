"""Trader-protection data: economic calendar, risk profiles, journal, watchlists, alerts and their events.

User objects reference an *instrument* (not a venue listing), so a feed change never touches user data.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
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
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.market import Instrument

IMPACTS = ("high", "medium", "low", "holiday", "none")
SIDES = ("long", "short")
ALERT_KINDS = ("price_cross", "pct_move", "signal", "news")
DELIVERY_STATES = ("pending", "sent", "partial", "failed", "no_devices", "disabled")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class NewsEvent(Base):
    """Scheduled economic-calendar events. ``currency`` is the calendar's country code (USD, EUR, ..., All)."""

    __tablename__ = "news_events"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_news_events_source_external_id"),
        CheckConstraint(_in("impact", IMPACTS), name="impact"),
        Index("ix_news_events_currency_event_at", "currency", "event_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32))
    external_id: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(200))
    currency: Mapped[str] = mapped_column(String(8))
    impact: Mapped[str] = mapped_column(String(8))
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    forecast: Mapped[str | None] = mapped_column(String(32))
    previous: Mapped[str | None] = mapped_column(String(32))
    actual: Mapped[str | None] = mapped_column(String(32))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NewsItem(Base):
    """Market headlines (Market Pulse): title, link and tags only, never article text."""

    __tablename__ = "news_items"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_news_items_source_external_id"),
        CheckConstraint(_in("impact", ("high", "medium", "low")), name="impact"),
        CheckConstraint(_in("kind", ("central_bank", "regulator", "headline")), name="kind"),
        Index("ix_news_items_assets", "assets", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32))
    external_id: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(300))
    url: Mapped[str] = mapped_column(String(1000))
    kind: Mapped[str] = mapped_column(String(16))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    impact: Mapped[str] = mapped_column(String(8))
    impact_reason: Mapped[str] = mapped_column(String(80))
    assets: Mapped[list[str]] = mapped_column(ARRAY(String(12)), server_default=text("'{}'"))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NewsFeedStatus(Base):
    """Health of each headline feed, shown with the feed so a silent source is visible."""

    __tablename__ = "news_feed_status"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    last_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(80))
    items: Mapped[int | None] = mapped_column(Integer)


class RiskProfile(Base):
    """A user's risk rules; used by the risk calculator and the risk-status warnings."""

    __tablename__ = "risk_profiles"
    __table_args__ = (
        CheckConstraint("risk_per_trade_pct > 0 AND risk_per_trade_pct <= 100", name="risk_per_trade_pct"),
        CheckConstraint("max_daily_loss_pct > 0 AND max_daily_loss_pct <= 100", name="max_daily_loss_pct"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    account_currency: Mapped[str] = mapped_column(String(8), default="USD", server_default="USD")
    balance: Mapped[float | None] = mapped_column(Double)
    risk_per_trade_pct: Mapped[float] = mapped_column(Double, default=1.0, server_default="1")
    max_daily_loss_pct: Mapped[float] = mapped_column(Double, default=3.0, server_default="3")
    max_trades_per_day: Mapped[int] = mapped_column(SmallInteger, default=6, server_default="6")
    max_consecutive_losses: Mapped[int] = mapped_column(SmallInteger, default=3, server_default="3")
    leverage: Mapped[float | None] = mapped_column(Double)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())


class JournalEntry(TimestampMixin, Base):
    """One trade the user took (manually entered; no broker connection). P&L fields are computed server-side."""

    __tablename__ = "journal_entries"
    __table_args__ = (
        CheckConstraint(_in("side", SIDES), name="side"),
        CheckConstraint("quantity > 0", name="quantity"),
        CheckConstraint("(exit_price IS NULL) = (exit_at IS NULL)", name="exit_complete"),
        Index("ix_journal_entries_user_entry_at", "user_id", "entry_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id", ondelete="RESTRICT"))
    timeframe: Mapped[str | None] = mapped_column(ForeignKey("timeframes.code"))
    side: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[float] = mapped_column(Double)  # units of the base asset
    entry_price: Mapped[float] = mapped_column(Double)
    entry_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    exit_price: Mapped[float | None] = mapped_column(Double)
    exit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stop_loss: Mapped[float | None] = mapped_column(Double)
    take_profit: Mapped[float | None] = mapped_column(Double)
    fees: Mapped[float] = mapped_column(Double, default=0.0, server_default="0")  # account currency
    account_currency: Mapped[str] = mapped_column(String(8))
    fx_rate: Mapped[float | None] = mapped_column(Double)  # quote -> account currency used for P&L
    risk_account: Mapped[float | None] = mapped_column(Double)  # |entry - stop| x qty in account currency
    pnl_quote: Mapped[float | None] = mapped_column(Double)
    pnl_account: Mapped[float | None] = mapped_column(Double)  # after fees
    r_multiple: Mapped[float | None] = mapped_column(Double)
    signal_id: Mapped[int | None] = mapped_column(ForeignKey("signals.id", ondelete="SET NULL"))
    setup: Mapped[str | None] = mapped_column(String(64))
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(32)), default=list, server_default="{}")
    notes: Mapped[str | None] = mapped_column(Text)

    instrument: Mapped[Instrument] = relationship(lazy="joined")


class Watchlist(Base):
    __tablename__ = "watchlists"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_watchlists_user_name"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    items: Mapped[list[WatchlistItem]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", passive_deletes=True,
        order_by="(WatchlistItem.sort_order, WatchlistItem.id)")


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("watchlist_id", "instrument_id", name="uq_watchlist_items_list_instrument"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    watchlist_id: Mapped[int] = mapped_column(ForeignKey("watchlists.id", ondelete="CASCADE"), index=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id", ondelete="CASCADE"), index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    instrument: Mapped[Instrument] = relationship(lazy="joined")


class Alert(TimestampMixin, Base):
    """Generic alert: ``kind`` + ``params`` (validated per kind by app/schemas/tools.py). Scope is one
    instrument, or a watchlist (signal alerts), or neither (news alerts on all of a user's watchlists)."""

    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint(_in("kind", ALERT_KINDS), name="kind"),
        Index("ix_alerts_active_kind", "kind", postgresql_where=text("active")),
        Index("ix_alerts_instrument_id", "instrument_id", postgresql_where=text("active")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    instrument_id: Mapped[int | None] = mapped_column(ForeignKey("instruments.id", ondelete="CASCADE"))
    watchlist_id: Mapped[int | None] = mapped_column(ForeignKey("watchlists.id", ondelete="CASCADE"))
    timeframe: Mapped[str | None] = mapped_column(ForeignKey("timeframes.code"))
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    recurring: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    cooldown_s: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    note: Mapped[str | None] = mapped_column(String(120))
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trigger_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    instrument: Mapped[Instrument | None] = relationship(lazy="joined")


class AlertEvent(Base):
    """A fired alert: the in-app inbox and the push outbox. Unique per (alert, dedupe key)."""

    __tablename__ = "alert_events"
    __table_args__ = (
        UniqueConstraint("alert_id", "dedupe_key", name="uq_alert_events_alert_dedupe"),
        CheckConstraint(_in("delivery", DELIVERY_STATES), name="delivery"),
        Index("ix_alert_events_user_id_id", "user_id", "id"),
        Index("ix_alert_events_undelivered", "id", postgresql_where=text("delivery IN ('pending', 'failed')")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    alert_id: Mapped[int | None] = mapped_column(ForeignKey("alerts.id", ondelete="SET NULL"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(16))
    dedupe_key: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    delivery: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

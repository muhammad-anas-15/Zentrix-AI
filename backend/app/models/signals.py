"""Ingestion targets, model versions, live signals and their outcomes (the public track record)."""

from __future__ import annotations

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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.market import Instrument, InstrumentListing

OUTCOMES = ("win", "loss", "flat", "void")


class IngestionTarget(Base):
    """A (listing, timeframe) series the worker keeps up to date. Rows, not config: enabling a series is data."""

    __tablename__ = "ingestion_targets"
    __table_args__ = (
        UniqueConstraint("listing_id", "timeframe", name="uq_ingestion_targets_listing_timeframe"),
        CheckConstraint("reason IN ('model', 'htf', 'chart', 'manual')", name="reason"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("instrument_listings.id", ondelete="CASCADE"), index=True)
    timeframe: Mapped[str] = mapped_column(ForeignKey("timeframes.code"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    priority: Mapped[int] = mapped_column(SmallInteger, default=100, server_default="100")  # lower runs first
    reason: Mapped[str] = mapped_column(String(16))
    backfill_candles: Mapped[int] = mapped_column(Integer, default=700, server_default="700")
    # Set: never fetched; built by the worker from this listing's stored candles of that (finer) timeframe.
    derive_from: Mapped[str | None] = mapped_column(ForeignKey("timeframes.code"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    listing: Mapped[InstrumentListing] = relationship(lazy="joined")


class ModelVersion(Base):
    """A trained artifact registered for live use (mirrors ml/artifacts/<key>/metadata.json)."""

    __tablename__ = "model_versions"
    __table_args__ = (
        UniqueConstraint("key", "trained_at", name="uq_model_versions_key_trained_at"),
        CheckConstraint("label_mode IN ('open_to_open', 'close_to_close')", name="label_mode"),
        # one active model per series and horizon
        Index("uq_model_versions_active_series", "listing_id", "timeframe", "horizon", unique=True,
              postgresql_where=text("active")),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64))
    listing_id: Mapped[int] = mapped_column(ForeignKey("instrument_listings.id", ondelete="RESTRICT"), index=True)
    timeframe: Mapped[str] = mapped_column(ForeignKey("timeframes.code"))
    horizon: Mapped[int] = mapped_column(SmallInteger)
    htf_timeframe: Mapped[str | None] = mapped_column(ForeignKey("timeframes.code"))
    label_mode: Mapped[str] = mapped_column(String(16))
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    git_commit: Mapped[str | None] = mapped_column(String(40))
    walk_forward_run_id: Mapped[str | None] = mapped_column(String(64))
    usable: Mapped[bool] = mapped_column(Boolean)  # demonstrated out-of-sample edge (usability gate)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB)
    calibration: Mapped[dict[str, Any]] = mapped_column(JSONB)
    strength: Mapped[dict[str, Any]] = mapped_column(JSONB)
    usability: Mapped[dict[str, Any]] = mapped_column(JSONB)
    active: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    note: Mapped[str | None] = mapped_column(Text)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    listing: Mapped[InstrumentListing] = relationship(lazy="joined")


class Signal(Base):
    """One live prediction for one closed candle. Created only within one timeframe of the candle's close."""

    __tablename__ = "signals"
    __table_args__ = (
        UniqueConstraint("model_version_id", "candle_ts", name="uq_signals_model_version_candle"),
        CheckConstraint("direction IN ('up', 'down')", name="direction"),
        Index("ix_signals_series_candle_ts", "listing_id", "timeframe", "horizon", "candle_ts"),
        Index("ix_signals_instrument_candle_ts", "instrument_id", "candle_ts"),
        Index("ix_signals_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    model_version_id: Mapped[int] = mapped_column(ForeignKey("model_versions.id", ondelete="RESTRICT"))
    listing_id: Mapped[int] = mapped_column(ForeignKey("instrument_listings.id", ondelete="RESTRICT"))
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id", ondelete="RESTRICT"))
    timeframe: Mapped[str] = mapped_column(ForeignKey("timeframes.code"))
    horizon: Mapped[int] = mapped_column(SmallInteger)
    candle_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # open time of the signal candle
    decision_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # its close
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    direction: Mapped[str] = mapped_column(String(4))
    p_up_raw: Mapped[float] = mapped_column(Double)
    p_up: Mapped[float] = mapped_column(Double)  # calibrated
    confidence: Mapped[float] = mapped_column(Double)  # calibrated probability of the stated direction
    strength: Mapped[str] = mapped_column(String(24))
    model_usable: Mapped[bool] = mapped_column(Boolean)
    features: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")

    model_version: Mapped[ModelVersion] = relationship(lazy="joined")
    listing: Mapped[InstrumentListing] = relationship(lazy="joined")
    instrument: Mapped[Instrument] = relationship(lazy="joined")
    outcome: Mapped[SignalOutcome | None] = relationship(lazy="joined", uselist=False)


class SignalOutcome(Base):
    """Resolved per the model's label: entry = open of candle t+1, exit = open of candle t+h+1."""

    __tablename__ = "signal_outcomes"
    __table_args__ = (CheckConstraint("outcome IN ('win', 'loss', 'flat', 'void')", name="outcome"),)

    signal_id: Mapped[int] = mapped_column(ForeignKey("signals.id", ondelete="CASCADE"), primary_key=True)
    outcome: Mapped[str] = mapped_column(String(8))
    entry_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    entry_price: Mapped[float | None] = mapped_column(Double)
    exit_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exit_price: Mapped[float | None] = mapped_column(Double)
    move: Mapped[float | None] = mapped_column(Double)  # exit - entry
    move_pct: Mapped[float | None] = mapped_column(Double)
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    note: Mapped[str | None] = mapped_column(Text)

"""Candles, signals, latest signal, live track record and model transparency. Public (tier limits: Phase 4)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DbDep
from app.core.errors import AppError
from app.core.ratelimit import limit_by_ip
from app.models.market import Candle, Instrument, InstrumentListing, Venue
from app.models.signals import ModelVersion, Signal, SignalOutcome
from app.schemas.signals import (
    BacktestOut,
    CandleOut,
    CandlesOut,
    ModelOut,
    SignalOut,
    SignalPage,
    TrackRecordOut,
)
from app.services.signals.cache import get_cached, latest_key, set_cached, track_record_version
from app.services.signals.serialize import signal_to_dict
from app.services.signals.track_record import Filters, compute_track_record

router = APIRouter(dependencies=[Depends(limit_by_ip("public", "rate_limit_public"))])
Symbol = Annotated[str, Query(min_length=3, max_length=40, description="Canonical symbol, e.g. EUR/USD, BTC/USDT:PERP")]
TimeframeQ = Annotated[str, Query(max_length=8, description="e.g. 15m")]


async def _listing(db: DbDep, symbol: str, venue: str | None) -> tuple[InstrumentListing, str]:
    stmt = (select(InstrumentListing, Venue.code).join(Instrument, Instrument.id == InstrumentListing.instrument_id)
            .join(Venue, Venue.id == InstrumentListing.venue_id).where(Instrument.symbol == symbol))
    stmt = stmt.where(Venue.code == venue) if venue else stmt.where(InstrumentListing.is_primary)
    row = (await db.execute(stmt)).first()
    if row is None:
        raise AppError(404, "unknown_instrument", f"No {'listing on ' + venue if venue else 'instrument'} for {symbol}")
    return row[0], row[1]


@router.get("/candles", response_model=CandlesOut, tags=["market"], summary="Closed candles for charts")
async def get_candles(db: DbDep, symbol: Symbol, timeframe: TimeframeQ,
                      venue: Annotated[str | None, Query(max_length=32)] = None,
                      limit: Annotated[int, Query(ge=1, le=1000)] = 300,
                      end: Annotated[datetime | None, Query(description="Only candles opening at/before")] = None,
                      ) -> CandlesOut:
    listing, venue_code = await _listing(db, symbol, venue)
    stmt = select(Candle).where(Candle.listing_id == listing.id, Candle.timeframe == timeframe)
    if end is not None:
        stmt = stmt.where(Candle.ts <= end)
    rows = (await db.scalars(stmt.order_by(Candle.ts.desc()).limit(limit))).all()
    return CandlesOut(symbol=symbol, venue=venue_code, timeframe=timeframe, candles=[
        CandleOut(t=c.ts, o=c.open, h=c.high, l=c.low, c=c.close, v=c.volume) for c in reversed(rows)])


@router.get("/signals", response_model=SignalPage, tags=["signals"],
            summary="Signal history with outcomes (the public track record, newest first)")
async def list_signals(
    db: DbDep,
    symbol: Annotated[str | None, Query(max_length=40)] = None,
    timeframe: Annotated[str | None, Query(max_length=8)] = None,
    horizon: Annotated[int | None, Query(ge=1, le=50)] = None,
    strength: Annotated[str | None, Query(max_length=24)] = None,
    status: Annotated[Literal["all", "pending", "resolved"], Query()] = "all",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    before_id: Annotated[int | None, Query(ge=1, description="Cursor: next_before_id of the previous page")] = None,
) -> SignalPage:
    stmt = select(Signal).join(Instrument, Instrument.id == Signal.instrument_id)
    if symbol:
        stmt = stmt.where(Instrument.symbol == symbol)
    if timeframe:
        stmt = stmt.where(Signal.timeframe == timeframe)
    if horizon:
        stmt = stmt.where(Signal.horizon == horizon)
    if strength:
        stmt = stmt.where(Signal.strength == strength)
    if status != "all":
        resolved = select(SignalOutcome.signal_id).where(SignalOutcome.signal_id == Signal.id).exists()
        stmt = stmt.where(resolved if status == "resolved" else ~resolved)
    if before_id:
        stmt = stmt.where(Signal.id < before_id)
    rows = (await db.scalars(stmt.order_by(Signal.id.desc()).limit(limit + 1))).unique().all()
    page = rows[:limit]
    return SignalPage(items=[SignalOut.model_validate(signal_to_dict(s)) for s in page],
                      next_before_id=page[-1].id if len(rows) > limit else None)


@router.get("/signals/latest", response_model=SignalOut, tags=["signals"], responses={404: {"description": "None yet"}},
            summary="Latest signal for an instrument/timeframe (cached)")
async def latest_signal(request: Request, db: DbDep, symbol: Symbol, timeframe: TimeframeQ,
                        horizon: Annotated[int, Query(ge=1, le=50)] = 1,
                        venue: Annotated[str | None, Query(max_length=32)] = None) -> SignalOut:
    listing, _ = await _listing(db, symbol, venue)
    cached = await get_cached(request.app.state.redis, latest_key(listing.id, timeframe, horizon))
    if cached is None:
        s = (await db.scalars(select(Signal).where(
            Signal.listing_id == listing.id, Signal.timeframe == timeframe, Signal.horizon == horizon)
            .order_by(Signal.candle_ts.desc()).limit(1))).unique().first()
        if s is None:
            raise AppError(404, "no_signal", f"No signal yet for {symbol} {timeframe}")
        cached = signal_to_dict(s)
    return SignalOut.model_validate(cached)


@router.get("/track-record", response_model=TrackRecordOut, tags=["signals"],
            summary="Live accuracy stats computed from stored signals and outcomes")
async def track_record(request: Request, db: DbDep,
                       symbol: Annotated[str | None, Query(max_length=40)] = None,
                       timeframe: Annotated[str | None, Query(max_length=8)] = None,
                       horizon: Annotated[int | None, Query(ge=1, le=50)] = None,
                       since: Annotated[datetime | None, Query()] = None) -> TrackRecordOut:
    f = Filters(symbol=symbol, timeframe=timeframe, horizon=horizon, since=since)
    redis = request.app.state.redis
    version = await track_record_version(redis)
    key = f"trackrecord:{version}:{f.cache_key()}"
    data: dict[str, Any] | None = await get_cached(redis, key) if version >= 0 else None
    if data is None:
        data = await compute_track_record(db, f)
        data["filters"] = {"symbol": symbol, "timeframe": timeframe, "horizon": horizon, "since": since}
        if version >= 0:
            await set_cached(redis, key, data, ttl_s=300)
    return TrackRecordOut.model_validate(data)


@router.get("/models", response_model=list[ModelOut], tags=["signals"],
            summary="Models behind the signals, with their out-of-sample backtest and edge assessment")
async def list_models(db: DbDep, symbol: Annotated[str | None, Query(max_length=40)] = None,
                      active_only: bool = True) -> list[ModelOut]:
    stmt = (select(ModelVersion, Instrument.symbol, Venue.code)
            .join(InstrumentListing, InstrumentListing.id == ModelVersion.listing_id)
            .join(Instrument, Instrument.id == InstrumentListing.instrument_id)
            .join(Venue, Venue.id == InstrumentListing.venue_id)
            .options(selectinload(ModelVersion.listing)))
    if symbol:
        stmt = stmt.where(Instrument.symbol == symbol)
    if active_only:
        stmt = stmt.where(ModelVersion.active)
    out = []
    for mv, sym, venue in (await db.execute(stmt.order_by(Instrument.symbol, ModelVersion.timeframe,
                                                          ModelVersion.horizon))).all():
        m = mv.metrics or {}
        acc = m.get("accuracy") or {}
        out.append(ModelOut(
            key=mv.key, symbol=sym, venue=venue, timeframe=mv.timeframe, horizon=mv.horizon, active=mv.active,
            has_demonstrated_edge=mv.usable, reasons=list(mv.usability.get("reasons", [])), label_mode=mv.label_mode,
            trained_at=mv.trained_at, note=mv.note,
            backtest=BacktestOut(oos_signals=m.get("n_oos"), accuracy=acc.get("rate"), ci95=acc.get("ci95"),
                                 majority_baseline=(m.get("baseline_accuracy") or {}).get("rate"),
                                 period=m.get("period"))))
    return out

"""Outcome resolver: applies each model's label to its signals once the needed candles exist.

open_to_open (current models): entry = open of the first market-hours candle after the signal candle,
exit = open of the (h+1)-th. close_to_close: entry = signal candle close, exit = close of the h-th candle.
win/loss = exit vs entry in the signal's direction; equal = flat. If candles are missing from the series
(ingestion gap) the slots no longer line up with the label, so the signal is voided rather than scored on the
wrong candles. Flat and void are excluded from the hit rate and reported.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market import Candle, Instrument, InstrumentListing
from app.models.signals import ModelVersion, Signal, SignalOutcome
from app.services.marketdata.candles import dt_to_ts
from ml.data.candles import interval_seconds
from ml.data.sessions import market_open_mask


def expected_slots(after_ts: int, timeframe: str, session: str, n: int) -> list[int]:
    """Open times of the next ``n`` market-hours candles after ``after_ts``."""
    step = interval_seconds(timeframe)
    out: list[int] = []
    cursor = after_ts
    while len(out) < n:
        block = pd.Series(range(cursor + step, cursor + step * 401, step))
        open_ = block[market_open_mask(block, session)].tolist()
        out.extend(open_[: n - len(out)])
        cursor = int(block.iloc[-1])
    return out


def _outcome(direction: str, entry: float, exit_: float) -> str:
    if exit_ == entry:
        return "flat"
    return "win" if (exit_ > entry) == (direction == "up") else "loss"


async def resolve_series(db: AsyncSession, listing_id: int, timeframe: str, now: float,
                         void_after_s: int = 6 * 3600) -> int:
    """Resolve pending signals of one series. Returns how many outcomes were written. Caller commits."""
    pending = (await db.execute(
        select(Signal, ModelVersion.label_mode, Instrument.session)
        .join(ModelVersion, ModelVersion.id == Signal.model_version_id)
        .join(InstrumentListing, InstrumentListing.id == Signal.listing_id)
        .join(Instrument, Instrument.id == InstrumentListing.instrument_id)
        .outerjoin(SignalOutcome, SignalOutcome.signal_id == Signal.id)
        .where(Signal.listing_id == listing_id, Signal.timeframe == timeframe, SignalOutcome.signal_id.is_(None))
        .order_by(Signal.candle_ts).limit(1000))).all()
    written = 0
    for sig, label_mode, session in pending:
        h = sig.horizon
        start = dt_to_ts(sig.candle_ts)
        need = h + 1 if label_mode == "open_to_open" else h
        slots = expected_slots(start, timeframe, session, need)
        rows = (await db.execute(select(Candle.ts, Candle.open, Candle.close).where(
            Candle.listing_id == listing_id, Candle.timeframe == timeframe, Candle.ts > sig.candle_ts)
            .order_by(Candle.ts).limit(need))).all()
        if len(rows) < need:
            if now > slots[-1] + interval_seconds(timeframe) + void_after_s:
                db.add(SignalOutcome(signal_id=sig.id, outcome="void", note="candles never arrived"))
                written += 1
            continue
        if [dt_to_ts(r.ts) for r in rows] != slots:
            db.add(SignalOutcome(signal_id=sig.id, outcome="void", note="missing candles in the label window"))
            written += 1
            continue
        if label_mode == "open_to_open":
            entry_ts, entry, exit_ts, exit_ = rows[0].ts, rows[0].open, rows[-1].ts, rows[-1].open
        else:
            signal_close = await db.scalar(select(Candle.close).where(
                Candle.listing_id == listing_id, Candle.timeframe == timeframe, Candle.ts == sig.candle_ts))
            entry_ts, entry, exit_ts, exit_ = sig.candle_ts, float(signal_close or 0), rows[-1].ts, rows[-1].close
        move = exit_ - entry
        db.add(SignalOutcome(
            signal_id=sig.id, outcome=_outcome(sig.direction, entry, exit_), entry_ts=entry_ts, entry_price=entry,
            exit_ts=exit_ts, exit_price=exit_, move=move, move_pct=move / entry * 100 if entry else None,
            resolved_at=datetime.fromtimestamp(now, tz=UTC)))
        written += 1
    return written

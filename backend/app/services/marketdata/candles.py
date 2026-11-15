"""Candle storage: upsert closed candles, read a series as the ML candle frame (``time`` = open, UTC epoch s)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pandas as pd
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market import Candle
from ml.data.candles import empty_frame, to_frame


def ts_to_dt(ts: int | float) -> datetime:
    return datetime.fromtimestamp(int(ts), tz=UTC)


def dt_to_ts(dt: datetime) -> int:
    return int(dt.timestamp())


async def upsert_candles(db: AsyncSession, listing_id: int, timeframe: str, candles: pd.DataFrame) -> int:
    """Insert or update candles (providers occasionally revise a just-closed candle). Creates any missing
    monthly partitions first. Caller commits."""
    if candles.empty:
        return 0
    first, last = ts_to_dt(candles["time"].min()), ts_to_dt(candles["time"].max())
    await db.execute(text("SELECT zx_ensure_candle_partitions(:a, :b)"),
                     {"a": date(first.year, first.month, 1), "b": date(last.year, last.month, 1)})
    rows = [{"listing_id": listing_id, "timeframe": timeframe, "ts": ts_to_dt(r.time), "open": r.open,
             "high": r.high, "low": r.low, "close": r.close,
             "volume": None if pd.isna(r.volume) else float(r.volume)}
            for r in candles.itertuples(index=False)]
    stmt = pg_insert(Candle).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Candle.listing_id, Candle.timeframe, Candle.ts],
        set_={c: stmt.excluded[c] for c in ("open", "high", "low", "close", "volume")} | {"ingested_at": func.now()},
    )
    await db.execute(stmt)
    return len(rows)


async def load_series(db: AsyncSession, listing_id: int, timeframe: str, limit: int,
                      until: datetime | None = None) -> pd.DataFrame:
    """The ``limit`` most recent candles with open time <= ``until``, ascending, as an ML candle frame."""
    stmt = select(Candle.ts, Candle.open, Candle.high, Candle.low, Candle.close, Candle.volume).where(
        Candle.listing_id == listing_id, Candle.timeframe == timeframe)
    if until is not None:
        stmt = stmt.where(Candle.ts <= until)
    rows = (await db.execute(stmt.order_by(Candle.ts.desc()).limit(limit))).all()
    if not rows:
        return empty_frame()
    return to_frame([{"time": dt_to_ts(r.ts), "open": r.open, "high": r.high, "low": r.low, "close": r.close,
                      "volume": r.volume or 0.0} for r in rows])


async def last_candle_times(db: AsyncSession) -> dict[tuple[int, str], int]:
    rows = (await db.execute(select(Candle.listing_id, Candle.timeframe, func.max(Candle.ts))
                             .group_by(Candle.listing_id, Candle.timeframe))).all()
    return {(lid, tf): dt_to_ts(ts) for lid, tf, ts in rows}

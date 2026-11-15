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


WEEK_S = 7 * 86400
MONDAY_OFFSET_S = 4 * 86400  # 1970-01-01 was a Thursday; weeks open on Monday 00:00 UTC


def bucket_open(times: pd.Series, tf_s: int) -> pd.Series:
    """Open time of the ``tf_s`` period containing each epoch time (UTC; weeks open on Monday)."""
    if tf_s == WEEK_S:
        return (times - MONDAY_OFFSET_S) // tf_s * tf_s + MONDAY_OFFSET_S
    return times // tf_s * tf_s


def aggregate(source: pd.DataFrame, tf_s: int, now_ts: float, drop_partial_first: bool = False) -> pd.DataFrame:
    """Closed ``tf_s`` candles built from finer closed candles: open of the first, highest high, lowest low,
    close of the last, summed volume. Periods still open at ``now_ts`` are left out. A market that closes inside a
    period (FX on Friday evening) yields a shorter final candle, like any broker chart."""
    if source.empty:
        return source
    df = source.sort_values("time")
    buckets = bucket_open(df["time"], tf_s)
    out = df.groupby(buckets.to_numpy()).agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                                             close=("close", "last"), volume=("volume", "sum"))
    out.index.name = "time"
    out = out.reset_index()
    if drop_partial_first and len(out) and int(df["time"].iloc[0]) != int(out["time"].iloc[0]):
        out = out.iloc[1:]  # history starts mid-period: that first candle would be incomplete
    return out[out["time"] + tf_s <= now_ts].reset_index(drop=True)


async def derive_candles(db: AsyncSession, listing_id: int, source_tf: str, target_tf: str, now_ts: float,
                         since_ts: int | None = None) -> int:
    """Build and store ``target_tf`` candles from stored ``source_tf`` candles of the same listing, from the period
    containing ``since_ts`` (None: the whole stored history). Returns rows upserted. Caller commits."""
    from ml.data.candles import interval_seconds

    tf_s = interval_seconds(target_tf)
    stmt = select(Candle.ts, Candle.open, Candle.high, Candle.low, Candle.close, Candle.volume).where(
        Candle.listing_id == listing_id, Candle.timeframe == source_tf)
    if since_ts is not None:
        start = int(bucket_open(pd.Series([since_ts]), tf_s).iloc[0])
        stmt = stmt.where(Candle.ts >= ts_to_dt(start))
    rows = (await db.execute(stmt.order_by(Candle.ts))).all()
    if not rows:
        return 0
    source = pd.DataFrame([{"time": dt_to_ts(r.ts), "open": r.open, "high": r.high, "low": r.low, "close": r.close,
                            "volume": r.volume or 0.0} for r in rows])
    return await upsert_candles(db, listing_id, target_tf,
                                aggregate(source, tf_s, now_ts, drop_partial_first=since_ts is None))


async def last_candle_times(db: AsyncSession) -> dict[tuple[int, str], int]:
    rows = (await db.execute(select(Candle.listing_id, Candle.timeframe, func.max(Candle.ts))
                             .group_by(Candle.listing_id, Candle.timeframe))).all()
    return {(lid, tf): dt_to_ts(ts) for lid, tf, ts in rows}

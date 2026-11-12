"""Historical candles for training, with a local parquet cache (backend/data_cache, gitignored).

Only CLOSED candles are ever returned. Forex history from Twelve Data is paged backwards; offline
exports (MT5, HistData, ...) can be imported with ``import_csv`` (see docs/DATA_SOURCES.md).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import pandas as pd

from ml.data.candles import (
    drop_unclosed,
    interval_seconds,
    is_forex,
    merge_frames,
    safe_symbol,
    to_frame,
)
from ml.data.sources import binance, twelvedata
from ml.settings import get_settings

log = logging.getLogger(__name__)

SECONDS_PER_MONTH = 30 * 86400


def cache_path(symbol: str, interval: str, cache_dir: Path | None = None) -> Path:
    cache_dir = cache_dir or get_settings().data_cache_dir
    provider = "twelvedata" if is_forex(symbol) else "binance"
    return cache_dir / "candles" / provider / f"{safe_symbol(symbol)}_{interval}.parquet"


def read_cache(symbol: str, interval: str, cache_dir: Path | None = None) -> pd.DataFrame:
    path = cache_path(symbol, interval, cache_dir)
    return to_frame(pd.read_parquet(path)) if path.exists() else to_frame([])


def write_cache(df: pd.DataFrame, symbol: str, interval: str, cache_dir: Path | None = None) -> Path:
    path = cache_path(symbol, interval, cache_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    to_frame(df).to_parquet(path, index=False)
    return path


def fetch_range(symbol: str, interval: str, start_ts: int, end_ts: int | None = None) -> pd.DataFrame:
    source = twelvedata if is_forex(symbol) else binance
    return source.fetch_range(symbol, interval, start_ts, end_ts)


def load_history(symbol: str, interval: str, months: float, now: float | None = None,
                 offline: bool = False, cache_dir: Path | None = None) -> pd.DataFrame:
    """Closed candles covering the last ``months`` months. Extends the cache forwards (and backwards
    if it starts too late) unless ``offline``; offline mode uses only what is cached/imported."""
    now = time.time() if now is None else now
    start_ts = int(now - months * SECONDS_PER_MONTH)
    step = interval_seconds(interval)
    cached = read_cache(symbol, interval, cache_dir)

    if not offline:
        parts = [cached]
        if cached.empty:
            parts.append(fetch_range(symbol, interval, start_ts))
        else:
            if cached["time"].iloc[0] > start_ts + step:
                parts.append(fetch_range(symbol, interval, start_ts, int(cached["time"].iloc[0])))
            parts.append(fetch_range(symbol, interval, int(cached["time"].iloc[-1])))
        merged = drop_unclosed(merge_frames(*parts), interval, now)  # never cache a forming candle
        if len(merged) > len(cached):
            write_cache(merged, symbol, interval, cache_dir)
        cached = merged

    df = drop_unclosed(cached, interval, now)
    df = df[df["time"] >= start_ts].reset_index(drop=True)
    log.info("%s %s: %d closed candles (%s -> %s)", symbol, interval, len(df),
             _fmt(df["time"].iloc[0]) if len(df) else "-", _fmt(df["time"].iloc[-1]) if len(df) else "-")
    return df


def import_csv(path: str | Path, symbol: str, interval: str, cache_dir: Path | None = None) -> Path:
    """Merge an offline OHLCV export into the cache. Expected columns: time (UTC epoch seconds or an
    ISO datetime in UTC, candle OPEN time), open, high, low, close[, volume]."""
    raw = pd.read_csv(path)
    raw.columns = [c.strip().lower() for c in raw.columns]
    if not pd.api.types.is_numeric_dtype(raw["time"]):
        # Resolution-independent (pandas 3 no longer defaults to nanoseconds).
        raw["time"] = (pd.to_datetime(raw["time"], utc=True) - pd.Timestamp(0, tz="UTC")) // pd.Timedelta(seconds=1)
    merged = merge_frames(read_cache(symbol, interval, cache_dir), to_frame(raw))
    return write_cache(merged, symbol, interval, cache_dir)


def _fmt(ts: int) -> str:
    return pd.Timestamp(int(ts), unit="s", tz="UTC").strftime("%Y-%m-%d %H:%M")

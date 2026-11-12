"""Candle frame conventions shared by every data source, the feature builder and inference.

A candle frame is a DataFrame with columns ``CANDLE_COLUMNS``, sorted by ``time`` and unique per ``time``.
``time`` is the candle OPEN time as UTC epoch seconds. A candle is closed once ``time + interval <= now``.
"""

from __future__ import annotations

import time as _time
from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd

INTERVAL_SECONDS: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}

# Higher timeframe used for the trend-confirmation feature.
HIGHER_TF: dict[str, str] = {"1m": "15m", "5m": "1h", "15m": "1h", "1h": "4h"}

CANDLE_COLUMNS = ["time", "open", "high", "low", "close", "volume"]


def interval_seconds(interval: str) -> int:
    try:
        return INTERVAL_SECONDS[interval]
    except KeyError:
        raise ValueError(f"Unsupported interval: {interval!r}") from None


def is_forex(symbol: str) -> bool:
    """Forex/metal pairs are written with a slash (EUR/USD, XAU/USD); crypto is not (BTCUSDT)."""
    return "/" in symbol


def safe_symbol(symbol: str) -> str:
    return symbol.replace("/", "_").upper()


def empty_frame() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="int64" if c == "time" else "float64") for c in CANDLE_COLUMNS})


def to_frame(rows: Iterable[Mapping[str, Any]] | pd.DataFrame) -> pd.DataFrame:
    """Normalise rows into a candle frame: typed, de-duplicated by time (last wins), sorted."""
    df = rows.copy() if isinstance(rows, pd.DataFrame) else pd.DataFrame(list(rows))
    if df.empty:
        return empty_frame()
    if "volume" not in df.columns:
        df["volume"] = 0.0
    df = df[CANDLE_COLUMNS].astype({"time": "int64", "open": "float64", "high": "float64",
                                     "low": "float64", "close": "float64", "volume": "float64"})
    df["volume"] = df["volume"].fillna(0.0)
    return df.drop_duplicates("time", keep="last").sort_values("time").reset_index(drop=True)


def drop_unclosed(df: pd.DataFrame, interval: str, now: float | None = None) -> pd.DataFrame:
    """Remove candles that have not closed yet at ``now`` (the still-forming candle)."""
    now = _time.time() if now is None else now
    closed = df["time"] + interval_seconds(interval) <= now
    return df.loc[closed].reset_index(drop=True)


def merge_frames(*frames: pd.DataFrame) -> pd.DataFrame:
    parts = [f for f in frames if f is not None and not f.empty]
    if not parts:
        return empty_frame()
    return to_frame(pd.concat(parts, ignore_index=True))

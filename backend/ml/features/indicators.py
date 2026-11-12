"""Vectorised technical indicators. Each function takes Series aligned on the candle index and returns a
Series where row i uses only rows <= i (causal), so the whole history is computed in one pass."""

from __future__ import annotations

import numpy as np
import pandas as pd


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Cutler's RSI (simple moving averages of gains/losses), matching the original implementation."""
    delta = close.diff()
    avg_gain = delta.clip(lower=0).rolling(period).mean()
    avg_loss = (-delta.clip(upper=0)).rolling(period).mean()
    out = 100 - 100 / (1 + avg_gain / avg_loss)
    return out.where(avg_loss != 0, 100.0).where(avg_gain.notna())


def ema(close: pd.Series, period: int) -> pd.Series:
    return close.ewm(span=period, adjust=False).mean()


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series]:
    line = ema(close, fast) - ema(close, slow)
    return line, line.ewm(span=signal, adjust=False).mean()


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def bollinger(close: pd.Series, period: int = 20, n_std: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = close.rolling(period).mean()
    std = close.rolling(period).std()
    return mid + n_std * std, mid, mid - n_std * std


def volume_change_pct(volume: pd.Series, period: int = 5) -> pd.Series:
    """% change of this candle's volume vs the mean of the previous ``period`` candles (0 if no volume)."""
    prev_mean = volume.shift(1).rolling(period).mean()
    out = (volume - prev_mean) / prev_mean * 100
    return out.where(prev_mean > 0, 0.0).where(prev_mean.notna()).replace([np.inf, -np.inf], 0.0)


def rolling_support_resistance(high: pd.Series, low: pd.Series, lookback: int = 20) -> tuple[pd.Series, pd.Series]:
    """(resistance, support) = highest high / lowest low of the last ``lookback`` candles incl. this one."""
    return high.rolling(lookback, min_periods=1).max(), low.rolling(lookback, min_periods=1).min()

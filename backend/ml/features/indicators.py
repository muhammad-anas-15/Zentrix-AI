"""
Standard technical indicators computed from a list of close prices
(or OHLC where needed). All functions take plain lists/arrays and
return the LATEST value unless noted otherwise.
"""
import numpy as np
import pandas as pd


def rsi(closes, period: int = 14) -> float:
    closes = pd.Series(closes)
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean().iloc[-1]
    avg_loss = loss.rolling(period).mean().iloc[-1]
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def ema(closes, period: int) -> float:
    return round(pd.Series(closes).ewm(span=period, adjust=False).mean().iloc[-1], 6)


def ema_series(closes, period: int) -> pd.Series:
    return pd.Series(closes).ewm(span=period, adjust=False).mean()


def macd(closes, fast: int = 12, slow: int = 26, signal: int = 9):
    macd_line = ema_series(closes, fast) - ema_series(closes, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return round(macd_line.iloc[-1], 6), round(signal_line.iloc[-1], 6)


def atr(highs, lows, closes, period: int = 14) -> float:
    highs, lows, closes = pd.Series(highs), pd.Series(lows), pd.Series(closes)
    prev_close = closes.shift(1)
    tr = pd.concat([
        highs - lows,
        (highs - prev_close).abs(),
        (lows - prev_close).abs()
    ], axis=1).max(axis=1)
    return round(tr.rolling(period).mean().iloc[-1], 6)


def bollinger_bands(closes, period: int = 20, std_dev: int = 2):
    closes = pd.Series(closes)
    sma = closes.rolling(period).mean()
    std = closes.rolling(period).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    return round(upper.iloc[-1], 6), round(sma.iloc[-1], 6), round(lower.iloc[-1], 6)


def volume_change(volumes, period: int = 5) -> float:
    """Percent change of latest volume vs average of previous N."""
    volumes = pd.Series(volumes)
    if len(volumes) < period + 1:
        return 0.0
    avg_prev = volumes.iloc[-period-1:-1].mean()
    if avg_prev == 0:
        return 0.0
    return round(((volumes.iloc[-1] - avg_prev) / avg_prev) * 100, 2)


if __name__ == "__main__":
    closes = list(np.linspace(100, 110, 40) + np.random.randn(40))
    print("RSI:", rsi(closes))
    print("EMA20:", ema(closes, 20))
    print("MACD:", macd(closes))
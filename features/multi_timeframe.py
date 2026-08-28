"""
Multi-timeframe confirmation: checks whether a HIGHER timeframe's trend
agrees with the current signal. Added as a feature so the ML model can
learn "higher-timeframe-confirmed setups tend to be more reliable."
"""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from data_pipeline.fetch_binance import fetch_binance_ohlcv, fetch_binance_history

HIGHER_TF_MAP = {"1m": "15m", "5m": "1h", "15m": "1h", "1h": "4h"}


def _ema_trend(closes: list) -> int:
    """1 if price above EMA20 (bullish), else 0."""
    ema20 = pd.Series(closes).ewm(span=20, adjust=False).mean().iloc[-1]
    return 1 if closes[-1] > ema20 else 0


def get_current_higher_tf_trend(symbol: str, base_interval: str) -> int:
    """LIVE use (orchestrator/agent.py): fetch recent higher-tf candles, return trend."""
    higher_tf = HIGHER_TF_MAP.get(base_interval)
    if not higher_tf:
        return 0
    if "/" in symbol:
        from data_pipeline.fetch_forex import fetch_forex_ohlcv
        forex_map = {"15m": "15min", "1h": "1h", "5m": "5min", "1m": "1min", "4h": "4h"}
        candles = fetch_forex_ohlcv(symbol, forex_map.get(higher_tf, higher_tf), outputsize=30)
    else:
        candles = fetch_binance_ohlcv(symbol, higher_tf, limit=30)
    closes = [c["close"] for c in candles]
    return _ema_trend(closes) if len(closes) >= 20 else 0


def build_higher_tf_series(symbol: str, base_interval: str, months: int) -> pd.DataFrame:
    """
    HISTORICAL use (dataset_builder.py): fetches higher-tf history once,
    computes rolling EMA20 trend at each point, returns a time-indexed
    DataFrame to merge onto the base-timeframe dataset via merge_asof.
    Works for both crypto (Binance) and forex (Twelve Data).
    """
    higher_tf = HIGHER_TF_MAP.get(base_interval)
    if not higher_tf:
        return pd.DataFrame(columns=["time", "higher_tf_bullish"])

    if "/" in symbol:  # forex
        from data_pipeline.fetch_forex import fetch_forex_ohlcv
        forex_map = {"15m": "15min", "1h": "1h", "5m": "5min", "1m": "1min", "4h": "4h"}
        candles = fetch_forex_ohlcv(symbol, forex_map.get(higher_tf, higher_tf), outputsize=5000)
    else:
        candles = fetch_binance_history(symbol, higher_tf, months=months + 1)

    closes = [c["close"] for c in candles]
    times = [c["time"] for c in candles]

    ema20 = pd.Series(closes).ewm(span=20, adjust=False).mean()
    trend = (pd.Series(closes) > ema20).astype(int)

    return pd.DataFrame({"time": times, "higher_tf_bullish": trend.values}).sort_values("time")


if __name__ == "__main__":
    print("Live trend (BTCUSDT, 15m base -> 1h higher):",
          get_current_higher_tf_trend("BTCUSDT", "15m"))
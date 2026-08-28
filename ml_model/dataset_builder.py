"""
Builds a labeled training dataset from historical candles.
Reuses Phase 1's fetch_binance + feature_builder — no external dataset needed.

For each point in time, features are computed using ONLY candles up to
that point (rolling window) to avoid lookahead bias. Label = did the
NEXT candle close higher than the current one (1 = up/green, 0 = down/red).
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from data_pipeline.fetch_binance import fetch_binance_history
from data_pipeline.fetch_forex import fetch_forex_ohlcv
from features.feature_builder import build_features
from features.multi_timeframe import build_higher_tf_series

WINDOW = 60
HISTORY_MONTHS = 12


def fetch_full_history(symbol: str, interval: str, months: int = HISTORY_MONTHS):
    if "/" in symbol:  # forex pair, e.g. 'EUR/USD'
        forex_interval = {"15m": "15min", "1h": "1h", "5m": "5min", "1m": "1min"}.get(interval, interval)
        return fetch_forex_ohlcv(symbol, forex_interval, outputsize=5000)  # Twelve Data max per call
    return fetch_binance_history(symbol, interval, months=months)


def build_dataset(symbol: str = "BTCUSDT", interval: str = "15m", months: int = HISTORY_MONTHS,
                   horizon: int = 1) -> pd.DataFrame:
    """
    horizon: how many candles ahead to check for the label.
             1 = next candle (default). 5 = "trend over next 5 candles" (Option B).
    """
    candles = fetch_full_history(symbol, interval, months=months)
    rows = []

    for i in range(WINDOW, len(candles) - horizon):
        window_candles = candles[i - WINDOW:i + 1]
        try:
            feats = build_features(window_candles)
        except ValueError:
            continue

        # Pattern sequence: last 3 candle patterns before the current one
        history = feats["candles_with_patterns"]
        prev_patterns = [c["pattern"] for c in history[-4:-1]] if len(history) >= 4 else ["None", "None", "None"]
        while len(prev_patterns) < 3:
            prev_patterns.insert(0, "None")
        feats["prev_pattern_1"], feats["prev_pattern_2"], feats["prev_pattern_3"] = prev_patterns

        feats.pop("candles_with_patterns", None)  # not needed for ML rows
        feats.pop("pattern_context", None)
        feats.pop("pattern_book_rule", None)
        # NOTE: current_price/resistance/support kept in row for reference
        # (used by backtest.py for returns) but excluded from ML feature_cols
        # in train.py/backtest.py — never fed as raw dollar values to the model.

        next_close = candles[i + horizon]["close"]
        current_close = candles[i]["close"]
        feats["label"] = 1 if next_close > current_close else 0
        feats["time"] = candles[i]["time"]
        rows.append(feats)

    df = pd.DataFrame(rows)
    df = pd.get_dummies(df, columns=["pattern", "prev_pattern_1", "prev_pattern_2", "prev_pattern_3"],
                         prefix=["pattern", "prev1", "prev2", "prev3"])

    # Merge multi-timeframe confirmation feature (crypto + forex both)
    higher_tf_df = build_higher_tf_series(symbol, interval, months)
    if not higher_tf_df.empty:
        df = df.sort_values("time")
        df = pd.merge_asof(df, higher_tf_df.sort_values("time"), on="time", direction="backward")
        df["higher_tf_bullish"] = df["higher_tf_bullish"].fillna(0).astype(int)

    return df


if __name__ == "__main__":
    df = build_dataset("BTCUSDT", "15m")
    print(df.shape)
    print(df.head())
    df.to_csv("ml_model/dataset_cache.csv", index=False)
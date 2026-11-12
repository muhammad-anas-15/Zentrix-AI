"""Higher-timeframe trend confirmation, using CLOSED higher-TF candles only.

Lookahead fix: the old code merged on candle OPEN time, so a 15m candle at 10:15 saw the 1h candle that
opened at 10:00 (and closes at 11:00), i.e. a close 45 minutes in the future. Now each higher-TF value
is stamped with the time it becomes known (its close), and each base row with its decision time (its own
close); a base row only sees higher-TF candles that had closed by then.
"""

from __future__ import annotations

import pandas as pd

from ml.data.candles import interval_seconds


def higher_tf_trend(htf_candles: pd.DataFrame, htf_interval: str, ema_period: int = 20) -> pd.DataFrame:
    """Per closed higher-TF candle: ``available_at`` (its close time) and ``higher_tf_bullish``
    (1 if close > EMA20 of closes, else 0). Pass only closed candles."""
    if htf_candles.empty:
        return pd.DataFrame({"available_at": pd.Series(dtype="int64"),
                             "higher_tf_bullish": pd.Series(dtype="float64")})
    close = htf_candles["close"].reset_index(drop=True)
    ema = close.ewm(span=ema_period, adjust=False).mean()
    return pd.DataFrame({
        "available_at": (htf_candles["time"].to_numpy() + interval_seconds(htf_interval)).astype("int64"),
        "higher_tf_bullish": (close > ema).astype("float64").to_numpy(),
    })


def attach_higher_tf(base_times: pd.Series, base_interval: str, htf_trend: pd.DataFrame) -> pd.Series:
    """For each base candle open time, the latest higher-TF trend known at the base candle's close.
    NaN when no higher-TF candle had closed yet."""
    decision = pd.DataFrame({"decision_time": (base_times.to_numpy() + interval_seconds(base_interval)).astype("int64"),
                             "_order": range(len(base_times))})
    merged = pd.merge_asof(decision.sort_values("decision_time"), htf_trend.sort_values("available_at"),
                           left_on="decision_time", right_on="available_at", direction="backward",
                           allow_exact_matches=True)
    return merged.sort_values("_order")["higher_tf_bullish"].reset_index(drop=True).set_axis(base_times.index)

"""Single feature pipeline shared by training and inference (feature parity by construction).

``compute_features`` returns one row per candle; row i uses only candles <= i and higher-TF candles that
closed by candle i's close. ``to_model_matrix`` turns rows into the exact model input (fixed column order
and fixed one-hot vocabulary), and is the only way either path builds model input.

Indicator warm-up: EMAs depend on where the series starts. Rows before ``WARMUP`` are dropped in training,
and inference computes on the last ``INFERENCE_LOOKBACK`` closed candles, which makes EMA start-up effects
negligible (seed weight of EMA50 after 500 bars ~ 2e-9). The parity test checks both paths agree.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ml.features import indicators as ind
from ml.features.multi_timeframe import attach_higher_tf
from ml.features.patterns import PATTERNS, detect_patterns

WARMUP = 500  # rows dropped at the start of a training series (>= INFERENCE_LOOKBACK)
INFERENCE_LOOKBACK = 500  # closed base candles used to compute a live signal
INFERENCE_HTF_LOOKBACK = 200  # closed higher-TF candles used for the trend feature

NUMERIC_FEATURES: tuple[str, ...] = (
    "rsi",
    "price_vs_ema20_pct",
    "price_vs_ema50_pct",
    "ema20_vs_ema50_pct",
    "macd_norm",
    "macd_signal_norm",
    "macd_hist_norm",
    "atr_pct",
    "price_vs_bollinger_upper_pct",
    "price_vs_bollinger_lower_pct",
    "bollinger_width_pct",
    "volume_change_pct",
    "price_vs_resistance_pct",
    "price_vs_support_pct",
    "higher_tf_bullish",
)
PREV_VOCAB: tuple[str, ...] = (*PATTERNS, "None")
# prev1 = previous candle's pattern, prev2 = two candles back, prev3 = three back.
CATEGORICAL: dict[str, tuple[str, ...]] = {
    "pattern": PATTERNS,
    "prev1": PREV_VOCAB,
    "prev2": PREV_VOCAB,
    "prev3": PREV_VOCAB,
}
REFERENCE_COLUMNS = ("time", "current_price", "resistance", "support")  # never model inputs


def feature_columns() -> list[str]:
    cols = list(NUMERIC_FEATURES)
    for prefix, vocab in CATEGORICAL.items():
        cols += [f"{prefix}_{v}" for v in vocab]
    return cols


def compute_features(candles: pd.DataFrame, interval: str, htf_trend: pd.DataFrame | None) -> pd.DataFrame:
    """Feature rows for every candle in ``candles`` (closed candles, sorted by time)."""
    c = candles.reset_index(drop=True)
    close, high, low = c["close"], c["high"], c["low"]
    ema20, ema50 = ind.ema(close, 20), ind.ema(close, 50)
    macd_line, macd_signal = ind.macd(close)
    bb_upper, bb_mid, bb_lower = ind.bollinger(close)
    resistance, support = ind.rolling_support_resistance(high, low)
    pattern = detect_patterns(c)

    f = pd.DataFrame({"time": c["time"], "current_price": close, "resistance": resistance, "support": support})
    f["rsi"] = ind.rsi(close)
    f["price_vs_ema20_pct"] = (close - ema20) / ema20 * 100
    f["price_vs_ema50_pct"] = (close - ema50) / ema50 * 100
    f["ema20_vs_ema50_pct"] = (ema20 - ema50) / ema50 * 100
    f["macd_norm"] = macd_line / close * 100
    f["macd_signal_norm"] = macd_signal / close * 100
    f["macd_hist_norm"] = (macd_line - macd_signal) / close * 100
    f["atr_pct"] = ind.atr(high, low, close) / close * 100
    f["price_vs_bollinger_upper_pct"] = (close - bb_upper) / close * 100
    f["price_vs_bollinger_lower_pct"] = (close - bb_lower) / close * 100
    f["bollinger_width_pct"] = (bb_upper - bb_lower) / bb_mid * 100
    f["volume_change_pct"] = ind.volume_change_pct(c["volume"])
    f["price_vs_resistance_pct"] = (close - resistance) / close * 100
    f["price_vs_support_pct"] = (close - support) / close * 100
    f["higher_tf_bullish"] = (attach_higher_tf(c["time"], interval, htf_trend)
                              if htf_trend is not None else np.nan)
    f["pattern"] = pattern
    for k in (1, 2, 3):
        f[f"prev{k}"] = pattern.shift(k).fillna("None")
    return f


def to_model_matrix(rows: pd.DataFrame, columns: list[str] | None = None) -> pd.DataFrame:
    """Exact model input: float64, columns in ``feature_columns()`` order. Raises on missing values or
    unknown categories instead of silently filling them (the old inference path filled missing with 0)."""
    columns = columns or feature_columns()
    missing = [c for c in NUMERIC_FEATURES if c not in rows.columns or rows[c].isna().any()]
    if missing:
        raise ValueError(f"Missing/NaN numeric features: {missing}")
    out = pd.DataFrame(index=rows.index)
    for name in NUMERIC_FEATURES:
        out[name] = rows[name].astype("float64")
    for prefix, vocab in CATEGORICAL.items():
        unknown = set(rows[prefix].unique()) - set(vocab)
        if unknown:
            raise ValueError(f"Unknown {prefix} values: {sorted(unknown)}")
        for v in vocab:
            out[f"{prefix}_{v}"] = (rows[prefix] == v).astype("float64")
    if list(out.columns) != columns:
        raise ValueError("Model feature columns differ from the pipeline's feature_columns()")
    return out

"""Live feature row for the latest CLOSED candle, via the same pipeline as training."""

from __future__ import annotations

import time as _time

import pandas as pd

from ml.data.candles import drop_unclosed
from ml.features.builder import INFERENCE_HTF_LOOKBACK, INFERENCE_LOOKBACK, compute_features
from ml.features.multi_timeframe import higher_tf_trend


class InsufficientData(ValueError):
    pass


def latest_feature_row(candles: pd.DataFrame, interval: str, htf_candles: pd.DataFrame | None,
                       htf_interval: str | None, now: float | None = None) -> pd.DataFrame:
    """One-row feature frame for the last closed candle at ``now``. The forming candle (and any
    higher-TF candle still open) is dropped first, so a signal never uses unfinished data."""
    now = _time.time() if now is None else now
    base = drop_unclosed(candles, interval, now).tail(INFERENCE_LOOKBACK)
    if len(base) < INFERENCE_LOOKBACK:
        raise InsufficientData(f"need {INFERENCE_LOOKBACK} closed {interval} candles, got {len(base)}")
    htf = None
    if htf_candles is not None and htf_interval:
        htf = higher_tf_trend(drop_unclosed(htf_candles, htf_interval, now).tail(INFERENCE_HTF_LOOKBACK),
                              htf_interval)
    return compute_features(base, interval, htf).iloc[[-1]].reset_index(drop=True)

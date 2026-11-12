"""Labelled datasets built from closed candles with the shared feature pipeline (vectorised: one pass
over the whole history instead of recomputing indicators for every window).

Label (horizon h): 1 if close[t+h] > close[t], 0 if lower. ``last_move_up`` feeds the naive
"repeat/reverse the last candle" baseline in the report (not a model input). Flat outcomes (equal closes) are neither up
nor down; they are excluded from training and from accuracy, and their rate is reported.
``label_known_at`` is when the label is observable (close time of candle t+h); walk-forward uses it to
purge training rows whose label overlaps the test period.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ml.data.candles import HIGHER_TF, interval_seconds
from ml.data.history import load_history
from ml.features.builder import NUMERIC_FEATURES, WARMUP, compute_features
from ml.features.multi_timeframe import higher_tf_trend


@dataclass(frozen=True)
class DatasetInfo:
    n_candles: int
    n_rows: int
    n_flat: int
    first_time: int | None
    last_time: int | None

    @property
    def flat_rate(self) -> float:
        labelled = self.n_rows + self.n_flat
        return self.n_flat / labelled if labelled else 0.0


def make_labels(candles: pd.DataFrame, interval: str, horizon: int) -> pd.DataFrame:
    close = candles["close"].reset_index(drop=True)
    future = close.shift(-horizon)
    label = np.where(future > close, 1.0, np.where(future < close, 0.0, np.nan))
    label[future.isna().to_numpy()] = np.nan
    known = candles["time"].reset_index(drop=True).shift(-horizon) + interval_seconds(interval)
    return pd.DataFrame({"label": label, "label_known_at": known,
                         "is_flat": (future == close).to_numpy()})


def build_dataset(candles: pd.DataFrame, interval: str, htf_candles: pd.DataFrame | None,
                  htf_interval: str | None, horizon: int = 1) -> tuple[pd.DataFrame, DatasetInfo]:
    htf = higher_tf_trend(htf_candles, htf_interval) if htf_candles is not None and htf_interval else None
    feats = compute_features(candles, interval, htf)
    df = pd.concat([feats, make_labels(candles, interval, horizon)], axis=1)
    # Naive baseline input: did the last candle close up? (known at decision time)
    df["last_move_up"] = (df["current_price"].diff() > 0).astype(int)
    df = df.iloc[WARMUP:]
    df["decision_time"] = df["time"] + interval_seconds(interval)
    usable = df.dropna(subset=[*NUMERIC_FEATURES, "label_known_at"])
    n_flat = int(usable["is_flat"].sum())
    out = usable.dropna(subset=["label"]).drop(columns="is_flat").reset_index(drop=True)
    out["label"] = out["label"].astype(int)
    out["label_known_at"] = out["label_known_at"].astype("int64")
    info = DatasetInfo(n_candles=len(candles), n_rows=len(out), n_flat=n_flat,
                       first_time=int(out["time"].iloc[0]) if len(out) else None,
                       last_time=int(out["time"].iloc[-1]) if len(out) else None)
    return out, info


def load_dataset(symbol: str, interval: str, horizon: int, months: float, offline: bool = False,
                 now: float | None = None) -> tuple[pd.DataFrame, DatasetInfo]:
    htf_interval = HIGHER_TF.get(interval)
    candles = load_history(symbol, interval, months, now=now, offline=offline)
    htf_candles = (load_history(symbol, htf_interval, months + 1, now=now, offline=offline)
                   if htf_interval else None)  # +1 month so the higher-TF EMA is warmed up
    return build_dataset(candles, interval, htf_candles, htf_interval, horizon)

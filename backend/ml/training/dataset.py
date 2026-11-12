"""Labelled datasets built from closed candles with the shared feature pipeline (vectorised: one pass
over the whole history instead of recomputing indicators for every window).

Label (horizon h, default ``entry="next_open"``): a signal is computed at the close of candle t; the earliest
price a trader can act on is the OPEN of candle t+1. Label = 1 if close[t+h] > open[t+1], 0 if lower.

Why not close[t+h] vs close[t] (the original label): in the Twelve Data feed the next candle's open reverses
the current candle's body far more often than chance, while the next candle's own body does not. A
close-to-close label therefore rewards predicting that close->next-open jump, which is a feed artifact
smaller than the spread and cannot be traded. ``entry="close"`` keeps the original definition for comparison.
``next_open_reversal_rate`` in DatasetInfo measures the artifact per series (0.5 = none).

Flat outcomes are neither up nor down; they are excluded from training and accuracy, and their rate is
reported. ``label_known_at`` (close time of candle t+h) lets walk-forward purge overlapping labels.
``last_move_up`` feeds the naive "repeat/reverse the last candle" baseline (not a model input).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from ml.data.candles import HIGHER_TF, interval_seconds
from ml.data.history import load_history
from ml.features.builder import NUMERIC_FEATURES, WARMUP, compute_features
from ml.features.multi_timeframe import higher_tf_trend

LabelEntry = Literal["next_open", "close"]


@dataclass(frozen=True)
class DatasetInfo:
    n_candles: int
    n_rows: int
    n_flat: int
    first_time: int | None
    last_time: int | None
    label_entry: str = "next_open"
    next_open_reversal_rate: float | None = None

    @property
    def flat_rate(self) -> float:
        labelled = self.n_rows + self.n_flat
        return self.n_flat / labelled if labelled else 0.0


def make_labels(candles: pd.DataFrame, interval: str, horizon: int,
                entry: LabelEntry = "next_open") -> pd.DataFrame:
    c = candles.reset_index(drop=True)
    exit_price = c["close"].shift(-horizon)
    entry_price = c["open"].shift(-1) if entry == "next_open" else c["close"]
    label = np.where(exit_price > entry_price, 1.0, np.where(exit_price < entry_price, 0.0, np.nan))
    label[(exit_price.isna() | entry_price.isna()).to_numpy()] = np.nan
    known = c["time"].shift(-horizon) + interval_seconds(interval)
    return pd.DataFrame({"label": label, "label_known_at": known,
                         "is_flat": (exit_price == entry_price).to_numpy()})


def next_open_reversal_rate(candles: pd.DataFrame) -> float | None:
    """Share of candles whose body is reversed by the jump to the next candle's open (0.5 = no artifact)."""
    body = np.sign(candles["close"] - candles["open"])
    gap = np.sign(candles["open"].shift(-1) - candles["close"])
    m = (body != 0) & (gap != 0) & gap.notna()
    return float((gap[m] == -body[m]).mean()) if m.any() else None


def build_dataset(candles: pd.DataFrame, interval: str, htf_candles: pd.DataFrame | None,
                  htf_interval: str | None, horizon: int = 1,
                  entry: LabelEntry = "next_open") -> tuple[pd.DataFrame, DatasetInfo]:
    htf = higher_tf_trend(htf_candles, htf_interval) if htf_candles is not None and htf_interval else None
    feats = compute_features(candles, interval, htf)
    df = pd.concat([feats, make_labels(candles, interval, horizon, entry)], axis=1)
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
                       last_time=int(out["time"].iloc[-1]) if len(out) else None,
                       label_entry=entry, next_open_reversal_rate=next_open_reversal_rate(candles))
    return out, info


def load_dataset(symbol: str, interval: str, horizon: int, months: float, offline: bool = False,
                 now: float | None = None, entry: LabelEntry = "next_open") -> tuple[pd.DataFrame, DatasetInfo]:
    htf_interval = HIGHER_TF.get(interval)
    candles = load_history(symbol, interval, months, now=now, offline=offline)
    htf_candles = (load_history(symbol, htf_interval, months + 1, now=now, offline=offline)
                   if htf_interval else None)  # +1 month so the higher-TF EMA is warmed up
    return build_dataset(candles, interval, htf_candles, htf_interval, horizon, entry)

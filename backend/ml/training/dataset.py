"""Labelled datasets built from closed candles with the shared feature pipeline (vectorised: one pass
over the whole history instead of recomputing indicators for every window).

Label (horizon h, default ``mode="open_to_open"``): a signal is computed at the close of candle t. Entry is
the OPEN of candle t+1 (first price a trader can act on); exit is the OPEN of candle t+h+1 (first price after
candle t+h closes). Label = 1 if exit > entry, 0 if lower.

Why the same price field at both ends: in the Twelve Data forex/gold feed, a candle's open sits systematically
below the previous close and bodies are up 54-61% of the time (Binance: 50%), i.e. open and close behave
like different sides of the bid/ask spread. Labels that mix fields inherit that offset (next-open -> close is
"up" ~55% for no market reason), and close-to-close labels inherit spread noise that a trivial "reverse the last
body" rule predicts 54-62% of the time. Open-to-open cancels the constant offset. ``mode="close_to_close"``
keeps the original definition for comparison. DatasetInfo records two feed checks (50% = clean).

Flat outcomes are excluded from training and accuracy; their rate is reported. ``label_known_at`` (open
time of candle t+h+1, or close of t+h for close_to_close) lets walk-forward purge overlapping labels.
``last_body_up`` feeds the naive "repeat/reverse the last candle" baseline (not a model input).
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

LabelMode = Literal["open_to_open", "close_to_close"]


@dataclass(frozen=True)
class DatasetInfo:
    n_candles: int
    n_rows: int
    n_flat: int
    first_time: int | None
    last_time: int | None
    label_mode: str = "open_to_open"
    body_up_share: float | None = None  # share of up candle bodies; ~50% on a clean feed
    next_open_reversal_rate: float | None = None  # next open jumps against the body; ~50% on a clean feed

    @property
    def flat_rate(self) -> float:
        labelled = self.n_rows + self.n_flat
        return self.n_flat / labelled if labelled else 0.0


def make_labels(candles: pd.DataFrame, interval: str, horizon: int,
                mode: LabelMode = "open_to_open") -> pd.DataFrame:
    c = candles.reset_index(drop=True)
    if mode == "open_to_open":
        entry, exit_ = c["open"].shift(-1), c["open"].shift(-(horizon + 1))
        known = c["time"].shift(-(horizon + 1))  # that open is known when candle t+h+1 starts
    elif mode == "close_to_close":
        entry, exit_ = c["close"], c["close"].shift(-horizon)
        known = c["time"].shift(-horizon) + interval_seconds(interval)
    else:
        raise ValueError(f"unknown label mode {mode!r}")
    label = np.where(exit_ > entry, 1.0, np.where(exit_ < entry, 0.0, np.nan))
    label[(exit_.isna() | entry.isna()).to_numpy()] = np.nan
    return pd.DataFrame({"label": label, "label_known_at": known, "is_flat": (exit_ == entry).to_numpy()})


def feed_checks(candles: pd.DataFrame) -> tuple[float | None, float | None]:
    """(share of up bodies, share of next opens that jump against the body). Both ~0.5 on a clean feed."""
    body = np.sign(candles["close"] - candles["open"])
    gap = np.sign(candles["open"].shift(-1) - candles["close"])
    nz = body[body != 0]
    m = (body != 0) & (gap != 0) & gap.notna()
    return (float((nz > 0).mean()) if len(nz) else None,
            float((gap[m] == -body[m]).mean()) if m.any() else None)


def build_dataset(candles: pd.DataFrame, interval: str, htf_candles: pd.DataFrame | None,
                  htf_interval: str | None, horizon: int = 1,
                  mode: LabelMode = "open_to_open") -> tuple[pd.DataFrame, DatasetInfo]:
    htf = higher_tf_trend(htf_candles, htf_interval) if htf_candles is not None and htf_interval else None
    feats = compute_features(candles, interval, htf)
    df = pd.concat([feats, make_labels(candles, interval, horizon, mode)], axis=1)
    # Naive baseline input: was the last candle's body up? (known at decision time)
    df["last_body_up"] = (candles["close"].to_numpy() > candles["open"].to_numpy()).astype(int)
    df = df.iloc[WARMUP:]
    df["decision_time"] = df["time"] + interval_seconds(interval)
    usable = df.dropna(subset=[*NUMERIC_FEATURES, "label_known_at"])
    n_flat = int(usable["is_flat"].sum())
    out = usable.dropna(subset=["label"]).drop(columns="is_flat").reset_index(drop=True)
    out["label"] = out["label"].astype(int)
    out["label_known_at"] = out["label_known_at"].astype("int64")
    up_share, reversal = feed_checks(candles)
    info = DatasetInfo(n_candles=len(candles), n_rows=len(out), n_flat=n_flat,
                       first_time=int(out["time"].iloc[0]) if len(out) else None,
                       last_time=int(out["time"].iloc[-1]) if len(out) else None,
                       label_mode=mode, body_up_share=up_share, next_open_reversal_rate=reversal)
    return out, info


def load_dataset(symbol: str, interval: str, horizon: int, months: float, offline: bool = False,
                 now: float | None = None, mode: LabelMode = "open_to_open") -> tuple[pd.DataFrame, DatasetInfo]:
    htf_interval = HIGHER_TF.get(interval)
    candles = load_history(symbol, interval, months, now=now, offline=offline)
    htf_candles = (load_history(symbol, htf_interval, months + 1, now=now, offline=offline)
                   if htf_interval else None)  # +1 month so the higher-TF EMA is warmed up
    return build_dataset(candles, interval, htf_candles, htf_interval, horizon, mode)

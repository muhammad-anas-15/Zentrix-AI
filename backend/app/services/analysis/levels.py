"""ATR-based stop-loss / take-profit levels and their historical base rate.

Stop = entry -/+ ``sl_atr`` x ATR(14); targets at ``r`` x the stop distance. The base rate replays these exact
rules on stored candles: for every past candle as an entry in the same direction (entry = its close, ATR at
that candle), did the target trade before the stop within ``max_bars`` candles? A candle touching both counts
as a loss (intrabar order is unknown). It is a property of the levels on this market, not a forecast and not
conditioned on any signal. Entries overlap, so the interval is optimistic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from ml.calibration.strength import wilson_interval
from ml.features.indicators import atr as atr_series

METHOD = ("Stop = entry -/+ k x ATR(14), targets = R multiples of the stop distance. Base rate = share of past "
          "entries in this direction (every stored candle) where the target traded before the stop within "
          "max_bars candles; candles touching both count as losses; overlapping entries (optimistic interval). "
          "A property of the levels on this market, not a forecast.")


@dataclass(frozen=True)
class Levels:
    side: str
    entry: float
    atr: float
    stop: float
    targets: list[tuple[float, float]]  # (R multiple, price)


def compute_levels(entry: float, atr_value: float, side: str, sl_atr: float, rr: tuple[float, ...]) -> Levels:
    sign = 1 if side == "long" else -1
    dist = sl_atr * atr_value
    return Levels(side, entry, atr_value, entry - sign * dist, [(r, entry + sign * r * dist) for r in rr])


def base_rate(candles: pd.DataFrame, side: str, sl_atr: float, r: float, max_bars: int = 50,
              n_entries: int = 1000, atr_period: int = 14) -> dict[str, Any]:
    high = candles["high"].to_numpy(float)
    low = candles["low"].to_numpy(float)
    close = candles["close"].to_numpy(float)
    a = atr_series(candles["high"], candles["low"], candles["close"], atr_period).to_numpy(float)
    n = len(close)
    first = max(atr_period, n - max_bars - n_entries)
    wins = losses = timeouts = 0
    for i in range(first, n - 1):
        if not np.isfinite(a[i]) or a[i] <= 0:
            continue
        end = min(n, i + 1 + max_bars)
        if end - (i + 1) < max_bars:  # not enough future candles yet
            continue
        lv = compute_levels(close[i], a[i], side, sl_atr, (r,))
        tp = lv.targets[0][1]
        hh, ll = high[i + 1:end], low[i + 1:end]
        if side == "long":
            hit_sl, hit_tp = ll <= lv.stop, hh >= tp
        else:
            hit_sl, hit_tp = hh >= lv.stop, ll <= tp
        sl_at = int(np.argmax(hit_sl)) if hit_sl.any() else max_bars
        tp_at = int(np.argmax(hit_tp)) if hit_tp.any() else max_bars
        if sl_at == max_bars and tp_at == max_bars:
            timeouts += 1
        elif tp_at < sl_at:
            wins += 1
        else:
            losses += 1
    decided = wins + losses
    lo, hi = wilson_interval(wins, decided) if decided else (None, None)
    # break-even hit rate for this R (ignoring costs): risk 1 to make r
    return {"r": r, "entries": decided + timeouts, "target_first": wins, "stop_first": losses,
            "neither_within_max_bars": timeouts, "max_bars": max_bars,
            "hit_rate": wins / decided if decided else None, "ci95": [lo, hi] if decided else None,
            "break_even_hit_rate": round(1 / (1 + r), 4)}

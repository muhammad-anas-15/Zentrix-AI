"""Exit advisor for an open position: rules over stored closed candles, the news guard and the latest signal.

Actions (most urgent first): ``consider_exit``, ``take_partial``, ``tighten_stop``, ``hold``. Every action
lists the rules that fired. Signals only count when their model has a demonstrated out-of-sample edge and
an earned strength tier; otherwise they are shown as ignored.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.services.news.guard import GuardResult
from ml.calibration.strength import NO_EDGE
from ml.features.indicators import atr as atr_series

TRAIL_ATR = 3.0
SPIKE_ATR = 2.5
METHOD = ("Rules: stop or target already traded; close beyond the recent 20-candle support/resistance against the "
          "position; high-impact news window; volatility spike (candle range > 2.5 x ATR); open profit in R; "
          "chandelier trailing stop = best price since entry -/+ 3 x ATR(14), suggested once it locks in profit; "
          "stop to entry at 1R; opposing signal only if its model has a demonstrated edge.")


def advise(candles: pd.DataFrame, side: str, entry: float, stop: float | None, take_profit: float | None,
           opened_at: int | None, guard: GuardResult, signal: dict[str, Any] | None) -> dict[str, Any]:
    s = 1 if side == "long" else -1
    a = atr_series(candles["high"], candles["low"], candles["close"]).to_numpy(float)
    atr_now = float(a[-1]) if np.isfinite(a[-1]) else None
    price = float(candles["close"].iloc[-1])
    since = candles[candles["time"] >= opened_at] if opened_at is not None else candles.iloc[-1:]
    if since.empty:
        since = candles.iloc[-1:]
    best = float(since["high"].max() if s == 1 else since["low"].min())
    worst = float(since["low"].min() if s == 1 else since["high"].max())

    exits: list[str] = []
    partial: list[str] = []
    tighten: list[str] = []
    info: list[str] = []
    dist = abs(entry - stop) if stop is not None else None
    r_now = (price - entry) * s / dist if dist else None
    suggested_stop: float | None = None

    if stop is not None and (worst - stop) * s <= 0:
        exits.append(f"price traded through your stop ({stop}) since entry: if the stop was live the trade is "
                     "already closed")
    if take_profit is not None and (best - take_profit) * s >= 0:
        partial.append(f"price reached your target ({take_profit}) since entry")
    prev = candles.iloc[-21:-1]
    if len(prev) >= 10:
        level = float(prev["low"].min() if s == 1 else prev["high"].max())
        if (price - level) * s < 0:
            exits.append(f"closed {'below recent support' if s == 1 else 'above recent resistance'} ({level:g}) "
                         "against your position")
    if guard.state == "blackout":
        exits.append("high-impact news window: spreads widen and price can gap through stops")
    elif guard.state == "caution":
        info.append("news: " + "; ".join(guard.reasons))
    elif guard.state == "unknown":
        info.append("news risk unknown (calendar unavailable)")
    if atr_now:
        rng = float(candles["high"].iloc[-1] - candles["low"].iloc[-1])
        if rng > SPIKE_ATR * atr_now:
            exits.append(f"volatility spike: last candle range is {rng / atr_now:.1f} x ATR")
    if r_now is not None and r_now >= 2:
        partial.append(f"open profit is {r_now:.1f}R")
    trail = best - s * TRAIL_ATR * atr_now if atr_now else None
    # the trailing stop only activates once it would lock in profit (beyond entry) and still sits behind price
    if (trail is not None and (trail - entry) * s > 0 and (price - trail) * s > 0
            and (stop is None or (trail - stop) * s > 0)):
        suggested_stop = trail
        tighten.append(f"ATR trailing stop ({TRAIL_ATR:g} x ATR from the best price since entry) is at {trail:g}")
    if r_now is not None and r_now >= 1 and stop is not None and (entry - stop) * s > 0 and (
            suggested_stop is None or (entry - suggested_stop) * s > 0):
        suggested_stop = entry
        tighten.append(f"open profit is {r_now:.1f}R: moving the stop to entry removes the risk")

    if signal is not None:
        opposes = (signal["direction"] == "up") != (s == 1)
        usable = signal["model"]["has_demonstrated_edge"] and signal["strength"] != NO_EDGE
        if opposes and usable:
            exits.append(f"latest {signal['timeframe']} signal points {signal['direction']} "
                         f"({signal['strength']}, {signal['confidence']:.0%})")
        elif opposes:
            info.append(f"latest signal points {signal['direction']}, but its model has no demonstrated edge: "
                        "ignored")

    action = ("consider_exit" if exits else "take_partial" if partial else "tighten_stop" if tighten else "hold")
    return {"action": action, "reasons": exits + partial + tighten or ["no exit rule fired"], "notes": info,
            "price": price, "atr": atr_now, "r_multiple": r_now, "best_price": best,
            "suggested_stop": suggested_stop, "trailing_stop": trail,
            "stop_distance_atr": (price - stop) * s / atr_now if stop is not None and atr_now else None,
            "target_distance_atr": (take_profit - price) * s / atr_now if take_profit is not None and atr_now
            else None}

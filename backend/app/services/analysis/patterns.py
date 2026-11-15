"""Technical Pattern Projection: the candlestick pattern on the last closed candles, the market structure, and what
happened over the next 1-5 candles after the same pattern in this market's stored history.

Patterns (fixed rules, the newest candle decides; three-candle patterns take precedence):
  Three White Soldiers / Three Black Crows: three strong same-colour bodies (body >= half the range), each closing
    beyond the previous close and opening inside (or at the edge of) the previous body.
  Bullish / Bearish Engulfing, Hammer, Shooting Star (pin bars), Doji: the same rules as the ML feature detector
    (``ml.features.patterns``), so a pattern means the same thing everywhere in the product.

Projection: for every past occurrence i of the pattern (with 1..steps future candles stored), the move of close,
high and low k candles later relative to close[i], in units of ATR(14) at i. The median close path and its
20th-80th percentile band, scaled by today's ATR and applied to the last close, are drawn as ghost candles. With
fewer than ``min_cases`` past occurrences the projection uses every candle (the typical range) and says so.

Base rate: share of past occurrences where price was on the pattern's side k candles later (flat moves excluded),
with a Wilson 95% interval, next to the same share over all candles (the baseline). "Edge" requires the interval
at the stricter level ``EDGE_Z`` (seven patterns are tested, so 95% alone would flag luck too often) to lie above
the baseline. Occurrences overlap in time, so true uncertainty is somewhat wider than shown. Descriptive history,
not a forecast.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from app.services.analysis.conditions import trend_state
from ml.calibration.strength import wilson_interval
from ml.features.indicators import atr, rsi
from ml.features.patterns import detect_patterns

LABEL = "Technical Pattern Projection (based on historical candlestick & ATR behaviour)"
METHOD = ("Pattern rules on the last closed candles (three-candle patterns first). Projection: after every past "
          "occurrence of the same pattern in this market's stored candles, the close, high and low 1-5 candles "
          "later in ATR units; the median path and its 20-80% band are scaled to today's ATR. Base rate: how often "
          "price was on the pattern's side k candles later, with a 95% interval, against the same rate for any "
          "candle. 'Edge' only when a stricter interval (seven patterns are tested) lies above that baseline. Past "
          "occurrences overlap in time, so the real uncertainty is wider. A description of history, not a "
          "prediction or a trade signal.")
QUANTILES = (0.2, 0.5, 0.8)
EDGE_Z = 2.69  # two-sided 0.05 / 7 patterns (Bonferroni)


@dataclass(frozen=True)
class PatternDef:
    key: str
    name: str
    bias: int  # +1 bullish, -1 bearish, 0 neutral
    candles: int
    meaning: str


PATTERNS: dict[str, PatternDef] = {p.key: p for p in [
    PatternDef("three_white_soldiers", "Three White Soldiers", 1, 3,
               "Three strong rising candles in a row: buyers in steady control."),
    PatternDef("three_black_crows", "Three Black Crows", -1, 3,
               "Three strong falling candles in a row: sellers in steady control."),
    PatternDef("bullish_engulfing", "Bullish Engulfing", 1, 2,
               "A rising candle whose body covers the previous falling one."),
    PatternDef("bearish_engulfing", "Bearish Engulfing", -1, 2,
               "A falling candle whose body covers the previous rising one."),
    PatternDef("hammer", "Hammer (bullish pin bar)", 1, 1,
               "Sellers pushed price down, buyers pulled it back: a long lower wick."),
    PatternDef("shooting_star", "Shooting Star (bearish pin bar)", -1, 1,
               "Buyers pushed price up, sellers pushed it back: a long upper wick."),
    PatternDef("doji", "Doji", 0, 1, "Open and close almost equal: indecision, no side implied."),
]}
_ML_NAMES = {"Doji": "doji", "Hammer": "hammer", "Shooting Star": "shooting_star",
             "Bullish Engulfing": "bullish_engulfing", "Bearish Engulfing": "bearish_engulfing"}


def classify(candles: pd.DataFrame) -> np.ndarray:
    """Pattern key per candle ('' = no classic pattern)."""
    keys = np.array([_ML_NAMES.get(n, "") for n in detect_patterns(candles)], dtype=object)
    o, h, low, c = (candles[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    if len(c) < 3:
        return keys
    body = np.abs(c - o)
    strong = body >= 0.5 * np.maximum(h - low, 1e-12)
    up, down = c > o, c < o
    i = np.arange(2, len(c))
    a, b = i - 2, i - 1
    soldiers = (up[a] & up[b] & up[i] & strong[a] & strong[b] & strong[i] & (c[b] > c[a]) & (c[i] > c[b])
                & (o[b] >= o[a]) & (o[b] <= c[a]) & (o[i] >= o[b]) & (o[i] <= c[b]))
    crows = (down[a] & down[b] & down[i] & strong[a] & strong[b] & strong[i] & (c[b] < c[a]) & (c[i] < c[b])
             & (o[b] <= o[a]) & (o[b] >= c[a]) & (o[i] <= o[b]) & (o[i] >= c[b]))
    keys[i[soldiers]] = "three_white_soldiers"
    keys[i[crows]] = "three_black_crows"
    return keys


def _structure(candles: pd.DataFrame, lookback: int = 20) -> dict[str, Any]:
    h = candles["high"].to_numpy(float)[-lookback:]
    low = candles["low"].to_numpy(float)[-lookback:]
    half = len(h) // 2
    swing = "range"
    if half >= 3:
        hh, hl = h[half:].max() > h[:half].max(), low[half:].min() > low[:half].min()
        lh, ll = h[half:].max() < h[:half].max(), low[half:].min() < low[:half].min()
        swing = "uptrend" if hh and hl else "downtrend" if lh and ll else "range"
    close = candles["close"]
    r = rsi(close).iloc[-1]
    trend = trend_state(candles)
    momentum = (float(close.iloc[-1]) / float(close.iloc[-11]) - 1) * 100 if len(close) > 11 else None
    return {"trend_regime": trend["regime"], "trend_direction": trend["direction"], "adx": trend["adx"],
            "swing": swing, "rsi": round(float(r), 1) if np.isfinite(r) else None,
            "momentum_pct": round(momentum, 3) if momentum is not None else None, "lookback": lookback}


def _side_rate(moves: np.ndarray, bias: int, z: float = 1.96) -> tuple[float | None, list[float] | None, int]:
    moved = moves[moves != 0]
    n = int(len(moved))
    if n == 0:
        return None, None, 0
    k = int((np.sign(moved) == bias).sum())
    lo, hi = wilson_interval(k, n, z)
    return k / n, [lo, hi], n


def outlook(candles: pd.DataFrame, steps: int = 5, min_cases: int = 30) -> dict[str, Any]:
    h, low, c = (candles[k].to_numpy(dtype=float) for k in ("high", "low", "close"))
    n = len(c)
    keys = classify(candles)
    atr_arr = atr(candles["high"], candles["low"], candles["close"]).to_numpy(float)
    key = str(keys[-1])
    pdef = PATTERNS.get(key)

    m = n - steps  # occurrences with every future candle stored
    idx = np.arange(max(m, 0))
    base_atr = atr_arr[idx]
    valid = np.isfinite(base_atr) & (base_atr > 0)
    ks = np.arange(1, steps + 1)
    fwd_c = (c[idx[:, None] + ks] - c[idx, None]) / base_atr[:, None] if m > 0 else np.empty((0, steps))
    fwd_h = (h[idx[:, None] + ks] - c[idx, None]) / base_atr[:, None] if m > 0 else np.empty((0, steps))
    fwd_l = (low[idx[:, None] + ks] - c[idx, None]) / base_atr[:, None] if m > 0 else np.empty((0, steps))
    pattern_mask = valid & (keys[idx] == key) if pdef else np.zeros(len(idx), bool)
    cases = int(pattern_mask.sum())
    use_pattern = pdef is not None and cases >= min_cases
    mask = pattern_mask if use_pattern else valid
    atr_now = float(atr_arr[-1]) if np.isfinite(atr_arr[-1]) else None

    projection = None
    if atr_now and mask.sum() >= min_cases:
        qc = np.quantile(fwd_c[mask], QUANTILES, axis=0)  # (3, steps)
        mh = np.median(fwd_h[mask], axis=0)
        ml = np.median(fwd_l[mask], axis=0)
        last, prev = float(c[-1]), float(c[-1])
        rows = []
        for j in range(steps):
            close_j = last + qc[1, j] * atr_now
            rows.append({"k": j + 1, "open": prev, "close": close_j,
                         "high": max(prev, close_j, last + mh[j] * atr_now),
                         "low": min(prev, close_j, last + ml[j] * atr_now),
                         "band_low": last + qc[0, j] * atr_now, "band_high": last + qc[2, j] * atr_now})
            prev = close_j
        projection = {"basis": "pattern" if use_pattern else "all_candles", "cases": int(mask.sum()),
                      "steps": rows, "band": [QUANTILES[0], QUANTILES[-1]]}

    base_rate = None
    if pdef is not None and pdef.bias != 0 and cases > 0:
        by_step: list[dict[str, Any]] = []
        for j in range(steps):
            rate, ci, used = _side_rate(fwd_c[pattern_mask, j], pdef.bias)
            base, _, _ = _side_rate(fwd_c[valid, j], pdef.bias)
            by_step.append({"k": j + 1, "rate": rate, "ci95": ci, "cases": used, "baseline": base})
        h_rate, h_ci, h_cases = _side_rate(fwd_c[pattern_mask, steps - 1], pdef.bias)
        h_base, _, _ = _side_rate(fwd_c[valid, steps - 1], pdef.bias)
        _, strict, _ = _side_rate(fwd_c[pattern_mask, steps - 1], pdef.bias, EDGE_Z)
        edge = bool(use_pattern and strict is not None and h_base is not None and strict[0] > h_base)
        base_rate = {"horizon": steps, "rate": h_rate, "ci95": h_ci, "cases": h_cases, "baseline": h_base,
                     "edge": edge, "by_step": by_step}

    pattern = None
    if pdef is not None:
        first = n - pdef.candles
        pattern = {"key": pdef.key, "name": pdef.name, "bias": pdef.bias, "candles": pdef.candles,
                   "meaning": pdef.meaning, "starts": int(candles["time"].iloc[first]),
                   "past_cases": cases, "enough_cases": use_pattern}
    return {"pattern": pattern, "structure": _structure(candles), "projection": projection, "base_rate": base_rate,
            "atr": atr_now, "last_close": float(c[-1]), "history": n, "min_cases": min_cases}

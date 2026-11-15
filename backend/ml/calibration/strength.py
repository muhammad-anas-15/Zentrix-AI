"""Signal strength labels derived from measured out-of-sample accuracy (not from raw model confidence).

A tier is earned per model: its cut is the lowest grid confidence ``t`` such that past out-of-sample
signals with confidence >= t (at least ``min_n`` of them) have a Wilson lower bound on hit rate at or
above the tier's level. The bound is Bonferroni-adjusted over the fixed threshold grid: scanning many cuts
otherwise finds a "significant" subset in pure noise (a test checks that a no-edge model earns no tier).
Tiers a model has not earned are never shown; everything below the lowest earned tier is
"Very Weak - Wait" (no demonstrated edge). The levels define what a label means, they are not accuracy
claims; the measured accuracy per tier is reported in docs/ML_REPORT.md and stored per model.
"""

from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np

# (label, required 95% Wilson lower bound of out-of-sample hit rate)
TIER_LEVELS: tuple[tuple[str, float], ...] = (
    ("Strong", 0.60),
    ("Good", 0.56),
    ("Moderate", 0.53),
    ("Weak", 0.50),
)
NO_EDGE = "Very Weak - Wait"
TIER_ORDER: tuple[str, ...] = (*(t for t, _ in TIER_LEVELS), NO_EDGE)
MIN_TIER_N = 100
THRESHOLD_GRID: tuple[float, ...] = tuple(round(0.50 + 0.01 * i, 2) for i in range(31))  # 0.50 .. 0.80
# One-sided 2.5% family-wise error over the grid (95% two-sided equivalent), Bonferroni.
TIER_Z = NormalDist().inv_cdf(1 - 0.025 / len(THRESHOLD_GRID))


def direction(p_up: np.ndarray) -> np.ndarray:
    """1 (Up) when calibrated P(up) >= 0.5, else 0 (Down)."""
    return (np.asarray(p_up, dtype=float) >= 0.5).astype(int)


def confidence(p_up: np.ndarray) -> np.ndarray:
    p = np.asarray(p_up, dtype=float)
    return np.maximum(p, 1 - p)


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (math.nan, math.nan)
    phat = k / n
    denom = 1 + z * z / n
    centre = (phat + z * z / (2 * n)) / denom
    half = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / denom
    return (centre - half, centre + half)


def derive_cuts(conf: np.ndarray, correct: np.ndarray, min_n: int = MIN_TIER_N) -> dict[str, float | None]:
    conf = np.asarray(conf, dtype=float)
    correct = np.asarray(correct, dtype=int)
    lower: dict[float, float] = {}
    for t in THRESHOLD_GRID:
        sel = conf >= t
        n = int(sel.sum())
        if n >= min_n:
            lower[t] = wilson_interval(int(correct[sel].sum()), n, z=TIER_Z)[0]

    cuts: dict[str, float | None] = {}
    for tier, level in TIER_LEVELS:
        ok = [t for t, lb in lower.items() if (lb > level if level == 0.5 else lb >= level)]
        cuts[tier] = min(ok) if ok else None
    return cuts


def assign_strength(conf: float | np.ndarray, cuts: dict[str, float | None]) -> np.ndarray:
    c = np.atleast_1d(np.asarray(conf, dtype=float))
    out = np.full(c.shape, NO_EDGE, dtype=object)
    for tier, _ in reversed(TIER_LEVELS):  # weakest first, stronger tiers overwrite
        cut = cuts.get(tier)
        if cut is not None:
            out[c >= cut] = tier
    return out

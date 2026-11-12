"""Out-of-sample metrics computed from walk-forward predictions. Used for both the model metadata and
docs/ML_REPORT.md, so every number shown comes from stored OOS predictions."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ml.calibration.strength import TIER_ORDER, confidence, direction, wilson_interval

RELIABILITY_BINS: tuple[float, ...] = (0.50, 0.52, 0.54, 0.56, 0.58, 0.60, 0.65, 1.0)


def _rate(correct: np.ndarray) -> dict[str, Any]:
    n, k = int(len(correct)), int(np.sum(correct))
    lo, hi = wilson_interval(k, n)
    return {"n": n, "correct": k, "rate": k / n if n else None, "ci95": [lo, hi] if n else None}


def reliability_table(p_up: np.ndarray, label: np.ndarray, bins: tuple[float, ...] = RELIABILITY_BINS) -> list[dict]:
    conf, correct = confidence(p_up), direction(p_up) == label
    rows = []
    for i, (lo, hi) in enumerate(zip(bins[:-1], bins[1:], strict=True)):
        last = i == len(bins) - 2
        m = (conf >= lo) & ((conf <= hi) if last else (conf < hi))
        rows.append({"bin": [lo, hi], "mean_confidence": float(conf[m].mean()) if m.any() else None,
                     **_rate(correct[m])})
    return rows


def expected_calibration_error(p_up: np.ndarray, label: np.ndarray) -> float:
    total = len(p_up)
    return float(sum(r["n"] / total * abs(r["mean_confidence"] - r["rate"])
                     for r in reliability_table(p_up, label) if r["n"]))


def _naive(last_move_up: np.ndarray, y: np.ndarray) -> dict[str, Any]:
    """Better of 'repeat the last candle' and 'reverse the last candle' on the same rows. Picking the better
    rule after the fact flatters the baseline, which makes beating it a stricter test for the model."""
    repeat = _rate(last_move_up == y)
    reverse = _rate(last_move_up != y)
    return {**(repeat if repeat["rate"] >= reverse["rate"] else reverse),
            "rule": "repeat last candle" if repeat["rate"] >= reverse["rate"] else "reverse last candle"}


def summarize(pred: pd.DataFrame) -> dict[str, Any]:
    """Headline numbers use blocks >= 2 (calibrated out-of-sample); tier stats use blocks >= 3."""
    cal = pred[pred["block"] >= 2]
    y = cal["label"].to_numpy(dtype=int)
    p_cal, p_raw = cal["p_cal"].to_numpy(dtype=float), cal["p_raw"].to_numpy(dtype=float)
    eps = 1e-12
    tiers = pred[pred["block"] >= 3]
    tier_stats = {}
    for tier in TIER_ORDER:
        sel = tiers[tiers["strength"] == tier]
        stats = _rate(direction(sel["p_cal"].to_numpy(dtype=float)) == sel["label"].to_numpy(dtype=int))
        tier_stats[tier] = {**stats, "share": len(sel) / len(tiers) if len(tiers) else None}
    return {
        "n_oos": int(len(cal)),
        "period": {"first_time": int(cal["time"].min()), "last_time": int(cal["time"].max())},
        "accuracy": _rate(direction(p_cal) == y),
        "raw_accuracy": _rate(direction(p_raw) == y),
        "baseline_accuracy": _rate(cal["majority_pred"].to_numpy(dtype=int) == y),
        "naive_baseline": _naive(cal["last_move_up"].to_numpy(dtype=int), y),
        "up_rate": float(y.mean()),
        "brier": float(np.mean((p_cal - y) ** 2)),
        "brier_raw": float(np.mean((p_raw - y) ** 2)),
        "log_loss": float(-np.mean(y * np.log(p_cal + eps) + (1 - y) * np.log(1 - p_cal + eps))),
        "ece_raw": expected_calibration_error(p_raw, y),
        "ece_cal": expected_calibration_error(p_cal, y),
        "reliability": reliability_table(p_cal, y),
        "per_block": [{"block": int(b), **_rate(direction(g["p_cal"].to_numpy(float)) == g["label"].to_numpy(int))}
                      for b, g in cal.groupby("block")],
        "tiers": tier_stats,
    }

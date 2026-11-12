"""Strict walk-forward evaluation: every prediction, calibration and strength cut is out-of-sample.

Rows are split chronologically into an initial training span followed by K test blocks B1..BK.
- Block k: an expanding-window model is trained on rows before Bk whose label was already known at Bk's
  first decision time (purges label overlap for horizon > 1) and predicts raw P(up) for Bk.
- Calibration: Bk (k >= 2) is calibrated by a calibrator fitted on the raw predictions of B1..B(k-1).
- Strength: Bk (k >= 3) gets tier labels from cuts derived on the calibrated predictions of B2..B(k-1).
So a prediction in Bk never depends on Bk's own outcomes. The production artifact is the model refit on
all rows, the calibrator fitted on all raw OOS predictions, and the cuts derived on all calibrated ones.

This replaces historical_simulator.py, which scored the model on its own training data.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from xgboost import XGBClassifier

from ml.calibration.calibrators import Calibrator, fit_calibrator
from ml.calibration.strength import MIN_TIER_N, assign_strength, confidence, derive_cuts, direction
from ml.features.builder import to_model_matrix
from ml.training.model import make_model


@dataclass(frozen=True)
class WalkForwardConfig:
    n_blocks: int = 6
    initial_train_frac: float = 0.4
    calibration: str = "platt"
    min_tier_n: int = MIN_TIER_N
    seed: int = 42

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WalkForwardResult:
    predictions: pd.DataFrame  # time, decision_time, block, label, p_raw, p_cal, strength, majority_pred,
    # n_train, last_move_up
    calibrator: Calibrator
    cuts: dict[str, float | None]
    config: WalkForwardConfig
    train_spans: list[dict[str, int]] = field(default_factory=list)


def block_bounds(n_rows: int, cfg: WalkForwardConfig) -> list[tuple[int, int]]:
    start = int(n_rows * cfg.initial_train_frac)
    size = (n_rows - start) // cfg.n_blocks
    if start < 1 or size < 1:
        raise ValueError(f"too few rows ({n_rows}) for {cfg.n_blocks} walk-forward blocks")
    return [(start + i * size, n_rows if i == cfg.n_blocks - 1 else start + (i + 1) * size)
            for i in range(cfg.n_blocks)]


def run_walk_forward(ds: pd.DataFrame, cfg: WalkForwardConfig | None = None) -> WalkForwardResult:
    cfg = cfg or WalkForwardConfig()
    ds = ds.sort_values("time").reset_index(drop=True)
    x, y = to_model_matrix(ds), ds["label"].to_numpy(dtype=int)
    parts, spans = [], []

    for k, (s, e) in enumerate(block_bounds(len(ds), cfg), start=1):
        first_decision = ds["decision_time"].iloc[s]
        train = (ds.index < s) & (ds["label_known_at"] <= first_decision)  # purge overlapping labels
        if train.sum() < 100 or len(np.unique(y[train])) < 2:
            raise ValueError(f"block {k}: not enough training rows")
        model = make_model(cfg.seed).fit(x[train], y[train])
        parts.append(pd.DataFrame({
            "time": ds["time"].iloc[s:e].to_numpy(), "decision_time": ds["decision_time"].iloc[s:e].to_numpy(),
            "block": k, "label": y[s:e], "p_raw": model.predict_proba(x.iloc[s:e])[:, 1],
            "majority_pred": int(y[train].mean() >= 0.5), "n_train": int(train.sum()),
            "last_move_up": ds["last_move_up"].iloc[s:e].to_numpy(dtype=int),
        }))
        spans.append({"block": k, "train_last_label_known_at": int(ds.loc[train, "label_known_at"].max()),
                      "test_first_decision_time": int(first_decision)})

    p = pd.concat(parts, ignore_index=True)
    p["p_cal"] = np.nan
    p["strength"] = None
    for k in range(2, cfg.n_blocks + 1):
        past = p["block"] < k
        cal = fit_calibrator(cfg.calibration, p.loc[past, "p_raw"].to_numpy(), p.loc[past, "label"].to_numpy())
        now = p["block"] == k
        p.loc[now, "p_cal"] = cal.predict(p.loc[now, "p_raw"].to_numpy())
    for k in range(3, cfg.n_blocks + 1):
        past = (p["block"] >= 2) & (p["block"] < k)
        cuts = _cuts(p[past], cfg.min_tier_n)
        now = p["block"] == k
        p.loc[now, "strength"] = assign_strength(confidence(p.loc[now, "p_cal"].to_numpy()), cuts)

    final_cal = fit_calibrator(cfg.calibration, p["p_raw"].to_numpy(), p["label"].to_numpy())
    final_cuts = _cuts(p[p["block"] >= 2], cfg.min_tier_n)
    return WalkForwardResult(predictions=p, calibrator=final_cal, cuts=final_cuts, config=cfg, train_spans=spans)


def _cuts(p: pd.DataFrame, min_n: int) -> dict[str, float | None]:
    p_cal = p["p_cal"].to_numpy(dtype=float)
    return derive_cuts(confidence(p_cal), direction(p_cal) == p["label"].to_numpy(), min_n=min_n)


def fit_final_model(ds: pd.DataFrame, seed: int = 42) -> XGBClassifier:
    """Production model: refit on every labelled row."""
    return make_model(seed).fit(to_model_matrix(ds), ds["label"].to_numpy(dtype=int))

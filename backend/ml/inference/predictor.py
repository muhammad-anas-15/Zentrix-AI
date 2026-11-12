"""Live signals: latest CLOSED candle -> shared features -> model -> calibrated P(up) -> earned strength tier.

Confidence shown to users is the calibrated probability; the strength label is the tier this model earned
out-of-sample, and ``track_record`` carries that tier's measured OOS hit rate from the model metadata
(never a hardcoded number). Not financial advice.
"""

from __future__ import annotations

import time as _time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ml.calibration.calibrators import calibrator_from_dict
from ml.calibration.strength import assign_strength, confidence
from ml.data.candles import HIGHER_TF, is_forex
from ml.data.sources import binance, twelvedata
from ml.features.builder import INFERENCE_HTF_LOOKBACK, INFERENCE_LOOKBACK, to_model_matrix
from ml.inference.features import latest_feature_row
from ml.training.model import load_artifact, model_key


@dataclass(frozen=True)
class Signal:
    symbol: str
    interval: str
    horizon: int
    candle_time: int  # open time (UTC epoch s) of the closed candle the signal is computed on
    direction: str  # "Up" | "Down"
    p_up_raw: float
    p_up: float  # calibrated
    confidence: float  # calibrated probability of the stated direction
    strength: str
    track_record: dict[str, Any] | None  # OOS stats of this strength tier for this model
    model_key: str
    model_trained_at: str
    features: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Predictor:
    def __init__(self, model: Any, metadata: dict[str, Any]) -> None:
        self.model = model
        self.meta = metadata
        self.calibrator = calibrator_from_dict(metadata["calibration"])
        self.cuts = metadata["strength"]["cuts"]

    @classmethod
    def load(cls, symbol: str, interval: str, horizon: int = 1, root: Path | None = None) -> Predictor:
        return cls(*load_artifact(model_key(symbol, interval, horizon), root))

    def predict_row(self, row: pd.DataFrame) -> Signal:
        x = to_model_matrix(row, self.meta["feature_cols"])
        p_raw = float(self.model.predict_proba(x)[0, 1])
        p_up = float(self.calibrator.predict(np.array([p_raw]))[0])
        conf = float(confidence(np.array([p_up]))[0])
        strength = str(assign_strength(conf, self.cuts)[0])
        r = row.iloc[0]
        return Signal(
            symbol=self.meta["symbol"], interval=self.meta["interval"], horizon=int(self.meta["horizon"]),
            candle_time=int(r["time"]), direction="Up" if p_up >= 0.5 else "Down", p_up_raw=p_raw, p_up=p_up,
            confidence=conf, strength=strength,
            track_record=self.meta["strength"]["tier_stats"].get(strength),
            model_key=self.meta["key"], model_trained_at=self.meta["trained_at"],
            features={k: (v.item() if hasattr(v, "item") else v) for k, v in r.items()},
        )


def fetch_recent(symbol: str, interval: str, limit: int) -> pd.DataFrame:
    source = twelvedata if is_forex(symbol) else binance
    return source.fetch_latest(symbol, interval, limit)


def latest_signal(symbol: str, interval: str, horizon: int = 1, now: float | None = None,
                  predictor: Predictor | None = None) -> Signal:
    """Signal for the last closed candle. Fetches enough history for warm-up (+2 for the forming candle)."""
    now = _time.time() if now is None else now
    predictor = predictor or Predictor.load(symbol, interval, horizon)
    htf_interval = HIGHER_TF.get(interval)
    candles = fetch_recent(symbol, interval, INFERENCE_LOOKBACK + 2)
    htf = fetch_recent(symbol, htf_interval, INFERENCE_HTF_LOOKBACK + 2) if htf_interval else None
    return predictor.predict_row(latest_feature_row(candles, interval, htf, htf_interval, now=now))

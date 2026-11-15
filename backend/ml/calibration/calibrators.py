"""Probability calibrators for P(up). JSON-serialisable (stored in model metadata / model_versions)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

MIN_CALIBRATION_ROWS = 200
_CLIP = 1e-6


class Calibrator(Protocol):
    def predict(self, p_raw: np.ndarray) -> np.ndarray: ...
    def to_dict(self) -> dict[str, Any]: ...


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), _CLIP, 1 - _CLIP)
    return np.log(p / (1 - p))


@dataclass(frozen=True)
class PlattCalibrator:
    """p_cal = sigmoid(a * logit(p_raw) + b). Two parameters: stable on small, noisy samples."""

    a: float
    b: float

    @classmethod
    def fit(cls, p_raw: np.ndarray, y: np.ndarray) -> PlattCalibrator:
        lr = LogisticRegression(C=1e6, max_iter=1000).fit(_logit(p_raw).reshape(-1, 1), np.asarray(y, dtype=int))
        return cls(a=float(lr.coef_[0, 0]), b=float(lr.intercept_[0]))

    def predict(self, p_raw: np.ndarray) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-(self.a * _logit(p_raw) + self.b)))

    def to_dict(self) -> dict[str, Any]:
        return {"method": "platt", "a": self.a, "b": self.b}


@dataclass(frozen=True)
class IsotonicCalibrator:
    """Monotone step function; needs more data than Platt."""

    x: tuple[float, ...]
    y: tuple[float, ...]

    @classmethod
    def fit(cls, p_raw: np.ndarray, y: np.ndarray) -> IsotonicCalibrator:
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(np.asarray(p_raw, float), y)
        return cls(x=tuple(map(float, iso.X_thresholds_)), y=tuple(map(float, iso.y_thresholds_)))

    def predict(self, p_raw: np.ndarray) -> np.ndarray:
        return np.interp(np.asarray(p_raw, dtype=float), self.x, self.y)

    def to_dict(self) -> dict[str, Any]:
        return {"method": "isotonic", "x": list(self.x), "y": list(self.y)}


def fit_calibrator(method: str, p_raw: np.ndarray, y: np.ndarray) -> Calibrator:
    if len(p_raw) < MIN_CALIBRATION_ROWS:
        raise ValueError(f"calibration needs >= {MIN_CALIBRATION_ROWS} out-of-sample rows, got {len(p_raw)}")
    if method == "platt":
        return PlattCalibrator.fit(p_raw, y)
    if method == "isotonic":
        return IsotonicCalibrator.fit(p_raw, y)
    raise ValueError(f"unknown calibration method {method!r}")


def calibrator_from_dict(d: dict[str, Any]) -> Calibrator:
    if d["method"] == "platt":
        return PlattCalibrator(a=d["a"], b=d["b"])
    if d["method"] == "isotonic":
        return IsotonicCalibrator(x=tuple(d["x"]), y=tuple(d["y"]))
    raise ValueError(f"unknown calibration method {d['method']!r}")

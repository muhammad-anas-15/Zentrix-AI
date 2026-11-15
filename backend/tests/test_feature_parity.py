"""Training rows and live inference rows must be the same features, in the same columns."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ml.features.builder import (
    CATEGORICAL,
    NUMERIC_FEATURES,
    feature_columns,
    to_model_matrix,
)
from ml.features.patterns import PATTERNS, detect_pattern, detect_patterns
from ml.inference.features import InsufficientData, latest_feature_row
from ml.training.dataset import build_dataset
from tests.conftest import make_candles, resample


@pytest.fixture(scope="module")
def series() -> tuple[pd.DataFrame, pd.DataFrame]:
    base = make_candles(3000, "15m", seed=7)
    return base, resample(base, "1h")


@pytest.mark.parametrize("row", [0, 150, 900, -1])
def test_training_row_equals_inference_row(series: tuple[pd.DataFrame, pd.DataFrame], row: int) -> None:
    base, htf = series
    ds, _ = build_dataset(base, "15m", htf, "1h", horizon=1)
    train_row = ds.iloc[row]
    # Inference sees only what existed at that candle's close: candles up to it, closed 1h candles.
    now = int(train_row["decision_time"])
    live = latest_feature_row(base[base["time"] <= train_row["time"]], "15m", htf, "1h", now=now).iloc[0]

    assert live["time"] == train_row["time"]
    for name in NUMERIC_FEATURES:
        assert live[name] == pytest.approx(train_row[name], rel=1e-7, abs=1e-7), name
    for name in CATEGORICAL:
        assert live[name] == train_row[name], name

    x_train = to_model_matrix(ds.iloc[[row]])
    x_live = to_model_matrix(pd.DataFrame([live]))
    assert list(x_train.columns) == list(x_live.columns) == feature_columns()
    np.testing.assert_allclose(x_train.to_numpy(), x_live.to_numpy(), rtol=1e-7, atol=1e-7)


def test_model_matrix_schema(series: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    base, htf = series
    ds, _ = build_dataset(base, "15m", htf, "1h", horizon=1)
    x = to_model_matrix(ds)
    assert list(x.columns) == feature_columns()
    assert (x.dtypes == "float64").all()
    for prefix, vocab in CATEGORICAL.items():
        onehot = x[[f"{prefix}_{v}" for v in vocab]]
        assert (onehot.sum(axis=1) == 1).all(), prefix
    # Fixed vocabulary: the column set never depends on which patterns happen to occur in the data.
    assert len(feature_columns()) == len(NUMERIC_FEATURES) + len(PATTERNS) + 3 * (len(PATTERNS) + 1)


def test_model_matrix_rejects_missing_or_unknown(series: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    base, htf = series
    ds, _ = build_dataset(base, "15m", htf, "1h", horizon=1)
    with pytest.raises(ValueError, match="Missing"):
        to_model_matrix(ds.iloc[:3].assign(rsi=np.nan))
    with pytest.raises(ValueError, match="Missing"):
        to_model_matrix(ds.iloc[:3].drop(columns="higher_tf_bullish"))
    with pytest.raises(ValueError, match="Unknown"):
        to_model_matrix(ds.iloc[:3].assign(pattern="Morning Star"))


def test_inference_requires_enough_history(series: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    base, htf = series
    with pytest.raises(InsufficientData):
        latest_feature_row(base.head(400), "15m", htf, "1h", now=int(base["time"].iloc[400]))


def test_vectorised_patterns_match_reference() -> None:
    candles = make_candles(3000, "5m", seed=11, decimals=4)
    special = pd.DataFrame([  # doji, hammer, shooting star, engulfings, zero-range candle
        {"time": 1, "open": 10.0, "high": 10.5, "low": 9.5, "close": 10.01, "volume": 0},
        {"time": 2, "open": 10.0, "high": 10.25, "low": 9.5, "close": 10.2, "volume": 0},
        {"time": 3, "open": 10.0, "high": 10.6, "low": 9.78, "close": 9.8, "volume": 0},
        {"time": 4, "open": 10.2, "high": 10.3, "low": 9.7, "close": 9.8, "volume": 0},
        {"time": 5, "open": 9.7, "high": 10.5, "low": 9.6, "close": 10.4, "volume": 0},
        {"time": 6, "open": 10.4, "high": 10.4, "low": 10.4, "close": 10.4, "volume": 0},
    ])
    for df in (candles, special):
        got = detect_patterns(df).tolist()
        prev = df.shift(1).fillna(df)
        want = [detect_pattern(r.open, r.high, r.low, r.close, p.open, p.close)
                for r, p in zip(df.itertuples(), prev.itertuples(), strict=True)]
        assert got == want
    assert set(detect_patterns(special)) >= {"Doji", "Hammer", "Shooting Star", "Bullish Engulfing"}

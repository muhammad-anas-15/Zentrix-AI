"""No feature or label may use information that was not available at the candle's close."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ml.data.candles import drop_unclosed
from ml.features.builder import NUMERIC_FEATURES, compute_features
from ml.features.multi_timeframe import attach_higher_tf, higher_tf_trend
from ml.inference.features import latest_feature_row
from ml.training.dataset import build_dataset, make_labels, next_open_reversal_rate
from tests.conftest import T0, make_candles, resample

H = 3600
M15 = 900


def test_higher_tf_uses_only_closed_candles() -> None:
    # Three 1h candles opening at T0, T0+1h, T0+2h with distinguishable trend values.
    htf = pd.DataFrame({"available_at": [T0 + H, T0 + 2 * H, T0 + 3 * H], "higher_tf_bullish": [1.0, 0.0, 1.0]})
    base_times = pd.Series([T0, T0 + H, T0 + H + 2 * M15, T0 + H + 3 * M15, T0 + 2 * H + 3 * M15])
    got = attach_higher_tf(base_times, "15m", htf).tolist()
    # 00:00-00:15 candle closes before any 1h candle closed -> unknown.
    assert np.isnan(got[0])
    # 01:00 candle (closes 01:15): the 01:00 1h candle is still open, so it sees the 00:00 one (1.0).
    assert got[1] == 1.0
    # 01:30 candle (closes 01:45): still the 00:00 1h candle.
    assert got[2] == 1.0
    # 01:45 candle closes at 02:00, exactly when the 01:00 1h candle closes -> may use it (0.0).
    assert got[3] == 0.0
    # 02:45 candle closes at 03:00 -> sees the 02:00 1h candle.
    assert got[4] == 1.0


def test_old_open_time_merge_would_leak(base_15m: pd.DataFrame, htf_1h: pd.DataFrame) -> None:
    """Regression guard: merging on open time (old behaviour) differs from the closed-candle merge."""
    trend = higher_tf_trend(htf_1h, "1h")
    leaky = pd.merge_asof(pd.DataFrame({"time": base_15m["time"]}),
                          trend.assign(time=htf_1h["time"].to_numpy()), on="time", direction="backward")
    fixed = attach_higher_tf(base_15m["time"], "15m", trend)
    assert (leaky["higher_tf_bullish"].to_numpy()[100:] != fixed.to_numpy()[100:]).any()


@pytest.mark.parametrize("cut", [600, 777, 1201])
def test_features_unchanged_when_future_is_altered(base_15m: pd.DataFrame, cut: int) -> None:
    """Perturb every candle after row ``cut`` and every higher-TF candle not closed at its close
    (including the forming one); features for rows <= cut must be bit-identical."""
    htf = resample(base_15m, "1h")
    decision = int(base_15m["time"].iloc[cut]) + M15
    original = compute_features(base_15m, "15m", higher_tf_trend(htf, "1h"))

    rng = np.random.default_rng(99)
    future_base = base_15m.copy()
    after = future_base.index > cut
    future_base.loc[after, ["open", "high", "low", "close"]] *= rng.uniform(0.9, 1.1, (after.sum(), 1))
    future_base.loc[after, "volume"] *= 7
    future_htf = htf.copy()
    not_closed = future_htf["time"] + H > decision
    future_htf.loc[not_closed, ["open", "high", "low", "close"]] *= 1.5

    altered = compute_features(future_base, "15m", higher_tf_trend(future_htf, "1h"))
    cols = [*NUMERIC_FEATURES, "pattern", "prev1", "prev2", "prev3"]
    pd.testing.assert_frame_equal(original.loc[:cut, cols], altered.loc[:cut, cols])


def _with_gaps(n: int, seed: int) -> pd.DataFrame:
    """Candles whose open differs from the previous close (like the real feed)."""
    c = make_candles(n, "15m", seed=seed, decimals=4)
    rng = np.random.default_rng(seed)
    c["open"] = (c["close"].shift(1).fillna(c["open"]) + rng.normal(0, 0.0003, n)).round(4)
    c["high"] = c[["open", "high", "close"]].max(axis=1)
    c["low"] = c[["open", "low", "close"]].min(axis=1)
    return c


@pytest.mark.parametrize("entry", ["next_open", "close"])
def test_labels_and_label_time(entry: str) -> None:
    candles = _with_gaps(60, seed=3)  # rounding creates flat outcomes
    labels = make_labels(candles, "15m", horizon=2, entry=entry)  # type: ignore[arg-type]
    for i in range(57):
        exit_ = candles["close"].iloc[i + 2]
        entry_px = candles["open"].iloc[i + 1] if entry == "next_open" else candles["close"].iloc[i]
        expected = 1.0 if exit_ > entry_px else 0.0 if exit_ < entry_px else np.nan
        got = labels["label"].iloc[i]
        assert got == expected or (np.isnan(expected) and np.isnan(got)), i
        assert labels["label_known_at"].iloc[i] == candles["time"].iloc[i + 2] + M15
    assert labels["label"].iloc[-2:].isna().all()


def test_next_open_label_ignores_close_to_open_jump() -> None:
    """A candle whose next open jumps against it: close-to-close says 'down', entry-based says 'up'."""
    c = pd.DataFrame({"time": [0, 900, 1800], "open": [1.0, 1.2, 1.3], "high": [1.5, 1.35, 1.4],
                      "low": [0.9, 1.15, 1.25], "close": [1.4, 1.3, 1.35], "volume": [0, 0, 0]})
    assert make_labels(c, "15m", 1, entry="next_open")["label"].iloc[0] == 1.0  # 1.2 -> 1.3
    assert make_labels(c, "15m", 1, entry="close")["label"].iloc[0] == 0.0  # 1.4 -> 1.3
    assert next_open_reversal_rate(c) == 1.0  # body up, next open below the close


def test_dataset_excludes_flats_and_unlabelled_rows() -> None:
    candles = make_candles(2000, "15m", seed=4, decimals=4)
    ds, info = build_dataset(candles, "15m", resample(candles, "1h"), "1h", horizon=1)
    assert info.n_flat > 0 and set(ds["label"].unique()) <= {0, 1}
    assert (ds["label_known_at"] > ds["decision_time"] - 1).all()
    assert ds["time"].max() < candles["time"].iloc[-1]  # last candle has no next candle -> no label


def test_drop_unclosed_removes_forming_candle() -> None:
    candles = make_candles(5, "15m")
    last_open = int(candles["time"].iloc[-1])
    assert len(drop_unclosed(candles, "15m", now=last_open + M15 - 1)) == 4  # still forming
    assert len(drop_unclosed(candles, "15m", now=last_open + M15)) == 5  # closed exactly now


def test_inference_ignores_forming_candles(base_15m: pd.DataFrame, htf_1h: pd.DataFrame) -> None:
    now = int(base_15m["time"].iloc[-1]) + M15  # last candle just closed
    expected = latest_feature_row(base_15m, "15m", htf_1h, "1h", now=now)
    # Live APIs also return the still-forming candle of each timeframe: wild values, must be ignored.
    forming_base = pd.DataFrame([{"time": now, "open": 9.0, "high": 99.0, "low": 0.1, "close": 50.0, "volume": 1e9}])
    forming_htf = pd.DataFrame([{"time": now - now % H, "open": 9.0, "high": 99.0, "low": 0.1, "close": 50.0,
                                 "volume": 1e9}])
    htf_live = pd.concat([htf_1h[htf_1h["time"] + H <= now], forming_htf], ignore_index=True)
    got = latest_feature_row(pd.concat([base_15m, forming_base], ignore_index=True), "15m",
                             htf_live, "1h", now=now + 60)
    pd.testing.assert_frame_equal(expected, got)

"""Walk-forward must be strictly out-of-sample for the model, the calibrator and the strength cuts."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ml.calibration import calibrators
from ml.calibration.calibrators import IsotonicCalibrator, PlattCalibrator, calibrator_from_dict, fit_calibrator
from ml.calibration.strength import NO_EDGE, TIER_Z, assign_strength, derive_cuts, wilson_interval
from ml.evaluation.metrics import expected_calibration_error, summarize
from ml.training import walk_forward as wf
from ml.training.dataset import build_dataset
from ml.training.walk_forward import WalkForwardConfig, block_bounds, run_walk_forward
from tests.conftest import make_candles, resample


@pytest.fixture(scope="module")
def dataset() -> pd.DataFrame:
    base = make_candles(6000, "15m", seed=21)
    ds, _ = build_dataset(base, "15m", resample(base, "1h"), "1h", horizon=3)
    return ds


def test_block_bounds_cover_tail_without_overlap() -> None:
    b = block_bounds(1000, WalkForwardConfig(n_blocks=6, initial_train_frac=0.4))
    assert b[0][0] == 400 and b[-1][1] == 1000
    assert all(e == s2 for (_, e), (s2, _) in zip(b[:-1], b[1:], strict=True))


def test_models_never_train_on_test_or_overlapping_labels(dataset: pd.DataFrame,
                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    fitted: list[pd.DataFrame] = []
    real = wf.make_model

    def spy(seed: int = 42):  # type: ignore[no-untyped-def]
        model = real(seed)
        orig_fit = model.fit

        def fit(x, y, **kw):  # type: ignore[no-untyped-def]
            fitted.append(x)
            return orig_fit(x, y, **kw)

        model.fit = fit
        return model

    monkeypatch.setattr(wf, "make_model", spy)
    cfg = WalkForwardConfig(n_blocks=4)
    res = run_walk_forward(dataset, cfg)
    for (s, _), x, span in zip(block_bounds(len(dataset), cfg), fitted, res.train_spans, strict=True):
        assert x.index.max() < s  # strictly before the test block
        # horizon=3: the last 3 rows before the block are purged (their label resolves inside it)
        assert x.index.max() <= s - 1 - 3 + 1
        assert span["train_last_label_known_at"] <= span["test_first_decision_time"]


def test_calibration_and_cuts_use_only_past_blocks(dataset: pd.DataFrame, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    real_fit = wf.fit_calibrator

    def spy(method: str, p_raw: np.ndarray, y: np.ndarray):  # type: ignore[no-untyped-def]
        calls.append(len(p_raw))
        return real_fit(method, p_raw, y)

    monkeypatch.setattr(wf, "fit_calibrator", spy)
    cfg = WalkForwardConfig(n_blocks=4)
    res = run_walk_forward(dataset, cfg)
    p = res.predictions
    sizes = p.groupby("block").size().to_numpy()
    # calibrator for block k is fitted on blocks 1..k-1 only; the final one on all blocks
    assert calls == [int(sizes[:k].sum()) for k in range(1, 4)] + [int(sizes.sum())]
    assert p.loc[p["block"] == 1, "p_cal"].isna().all() and p.loc[p["block"] >= 2, "p_cal"].notna().all()
    assert p.loc[p["block"] <= 2, "strength"].isna().all() and p.loc[p["block"] >= 3, "strength"].notna().all()


def test_future_outcomes_do_not_change_past_predictions(dataset: pd.DataFrame) -> None:
    cfg = WalkForwardConfig(n_blocks=4)
    a = run_walk_forward(dataset, cfg).predictions
    flipped = dataset.copy()
    last = block_bounds(len(dataset), cfg)[-1][0]
    flipped.loc[last:, "label"] = 1 - flipped.loc[last:, "label"]
    b = run_walk_forward(flipped, cfg).predictions
    early = a["block"] < 4
    pd.testing.assert_frame_equal(a.loc[early, ["p_raw", "p_cal", "strength"]],
                                  b.loc[early, ["p_raw", "p_cal", "strength"]])


def test_platt_fixes_overconfidence() -> None:
    rng = np.random.default_rng(0)
    true_p = rng.uniform(0.4, 0.6, 20_000)
    y = (rng.uniform(size=true_p.size) < true_p).astype(int)
    overconfident = 1 / (1 + np.exp(-4 * np.log(true_p / (1 - true_p))))  # spreads probabilities out
    cal = PlattCalibrator.fit(overconfident, y)
    assert expected_calibration_error(cal.predict(overconfident), y) < expected_calibration_error(overconfident, y) / 3
    assert cal.a == pytest.approx(0.25, abs=0.05)


@pytest.mark.parametrize("method", ["platt", "isotonic"])
def test_calibrator_round_trip(method: str) -> None:
    rng = np.random.default_rng(1)
    p, y = rng.uniform(size=500), rng.integers(0, 2, 500)
    cal = fit_calibrator(method, p, y)
    assert isinstance(cal, PlattCalibrator | IsotonicCalibrator)
    np.testing.assert_allclose(calibrator_from_dict(cal.to_dict()).predict(p), cal.predict(p))


def test_calibrator_refuses_tiny_samples() -> None:
    with pytest.raises(ValueError):
        fit_calibrator("platt", np.full(calibrators.MIN_CALIBRATION_ROWS - 1, 0.5),
                       np.zeros(calibrators.MIN_CALIBRATION_ROWS - 1))


def test_strength_cuts_require_measured_edge() -> None:
    rng = np.random.default_rng(2)
    conf = rng.uniform(0.5, 0.75, 20_000)
    correct = rng.uniform(size=conf.size) < conf  # perfectly calibrated
    cuts = derive_cuts(conf, correct, min_n=100)
    assert cuts["Weak"] is not None and cuts["Weak"] <= cuts["Moderate"] <= cuts["Good"] <= cuts["Strong"]  # type: ignore[operator]
    for tier, level in (("Strong", 0.60), ("Good", 0.56), ("Moderate", 0.53)):
        sel = correct[conf >= cuts[tier]]  # type: ignore[operator]
        assert wilson_interval(int(sel.sum()), len(sel), z=TIER_Z)[0] >= level
    # A model with no edge earns no tier at all, whatever its stated confidence.
    no_edge = derive_cuts(conf, rng.uniform(size=conf.size) < 0.5, min_n=100)
    assert all(v is None for v in no_edge.values())
    assert set(assign_strength(conf, no_edge)) == {NO_EDGE}


def test_summary_metrics(dataset: pd.DataFrame) -> None:
    res = run_walk_forward(dataset, WalkForwardConfig(n_blocks=4))
    m = summarize(res.predictions)
    assert m["n_oos"] == int((res.predictions["block"] >= 2).sum())
    assert sum(r["n"] for r in m["reliability"]) == m["n_oos"]
    assert sum(t["n"] for t in m["tiers"].values()) == int((res.predictions["block"] >= 3).sum())
    # Random-walk data has no edge: honest evaluation must not find one.
    assert m["accuracy"]["ci95"][0] < 0.5 + 0.03


def test_naive_baseline_is_better_of_repeat_and_reverse(dataset: pd.DataFrame) -> None:
    p = run_walk_forward(dataset, WalkForwardConfig(n_blocks=4)).predictions
    cal = p[p["block"] >= 2]
    repeat = float((cal["last_move_up"] == cal["label"]).mean())
    naive = summarize(p)["naive_baseline"]
    assert naive["rate"] == pytest.approx(max(repeat, 1 - repeat))
    assert naive["rule"] in {"repeat last candle", "reverse last candle"}
    # last_move_up only uses closes up to t
    ds = dataset
    assert ((ds["current_price"].diff() > 0).astype(int).iloc[1:] == ds["last_move_up"].iloc[1:]).mean() > 0.95

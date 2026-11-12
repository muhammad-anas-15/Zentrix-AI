from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from ml.data.sessions import market_open_mask, session_for_symbol, trading_hours_only
from ml.data.sources import twelvedata
from ml.evaluation.metrics import MAX_NAIVE_RATE, assess_usability, summarize
from ml.inference import predictor
from tests.conftest import make_candles

NY = ZoneInfo("America/New_York")


def _ts(*args: int) -> int:
    return int(datetime(*args, tzinfo=NY).timestamp())


@pytest.mark.parametrize("month_day", [(1, 9), (7, 10)])  # winter (EST) and summer (EDT) Fridays
def test_fx_week_boundaries_follow_new_york_time(month_day: tuple[int, int]) -> None:
    m, fri = month_day
    times = pd.Series([
        _ts(2026, m, fri, 16, 45),      # Friday 16:45 NY: open
        _ts(2026, m, fri, 17, 0),       # Friday 17:00 NY: closed
        _ts(2026, m, fri + 1, 12, 0),   # Saturday: closed
        _ts(2026, m, fri + 2, 16, 45),  # Sunday 16:45 NY: closed
        _ts(2026, m, fri + 2, 17, 0),   # Sunday 17:00 NY: open
        _ts(2026, m, fri + 3, 3, 0),    # Monday: open
    ])
    for session in ("fx_24x5", "metals_23x5", "commodities_23x5"):
        assert market_open_mask(times, session).tolist() == [True, False, False, False, True, True]
    assert market_open_mask(times, "crypto_24x7").all()  # crypto trades 24/7
    assert session_for_symbol("EUR/USD") == "fx_24x5" and session_for_symbol("BTCUSDT") == "crypto_24x7"
    with pytest.raises(ValueError, match="unknown session"):
        market_open_mask(times, "BTC/USDT")  # canonical DB symbols are not sessions


def test_live_fetch_applies_the_same_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    week = make_candles(7 * 96, "15m", start=_ts(2026, 3, 2, 0, 0))  # Monday..Sunday
    monkeypatch.setattr(twelvedata, "fetch_latest", lambda s, i, n: week.tail(n).reset_index(drop=True))
    got = predictor.fetch_recent("EUR/USD", "15m", 100)
    assert len(got) == 100 and market_open_mask(got["time"], "fx_24x5").all()
    pd.testing.assert_frame_equal(got, trading_hours_only(week, "fx_24x5").tail(100).reset_index(drop=True))


def _preds(n: int, model_acc: float, naive_acc: float, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    label = rng.integers(0, 2, n)
    correct = rng.uniform(size=n) < model_acc
    p_cal = np.where(correct == (label == 1), 0.56, 0.44)
    naive = np.where(rng.uniform(size=n) < naive_acc, label, 1 - label)
    return pd.DataFrame({"time": np.arange(n), "block": np.repeat(np.arange(1, 7), n // 6 + 1)[:n],
                         "label": label, "p_raw": p_cal, "p_cal": p_cal, "strength": "Weak",
                         "majority_pred": 1, "last_body_up": naive})


def test_gate_requires_beating_both_baselines() -> None:
    assert summarize(_preds(30_000, 0.56, 0.50))["usability"]["usable"]
    weak = summarize(_preds(30_000, 0.52, 0.52))["usability"]
    assert not weak["usable"] and "does not clear" in weak["reasons"][0]


def test_gate_rejects_feed_dominated_labels() -> None:
    # Model beats the naive rule, but the naive rule itself is far above chance: feed artifact, not skill.
    m = summarize(_preds(30_000, 0.66, MAX_NAIVE_RATE + 0.03))
    assert not m["usability"]["usable"]
    assert any("feed artifact" in r for r in assess_usability(m)["reasons"])


def test_tiers_are_served_only_if_they_held_out_of_sample() -> None:
    from ml.evaluation.metrics import served_cuts, validate_tiers

    rng = np.random.default_rng(3)
    n = 2_000
    label = rng.integers(0, 2, n)
    strength = np.where(np.arange(n) < 1_000, "Weak", "Very Weak - Wait")
    hit = np.where(strength == "Weak", rng.uniform(size=n) < 0.50, rng.uniform(size=n) < 0.53)  # Weak did not hold
    p_cal = np.where(hit == (label == 1), 0.52, 0.48)
    tiers = pd.DataFrame({"block": 3, "label": label, "p_cal": p_cal, "strength": strength})
    v = validate_tiers(tiers)
    assert not v["Weak"]["validated"]
    usable = {"usability": {"usable": True}, "tier_validation": v}
    assert served_cuts({"Strong": None, "Good": None, "Moderate": None, "Weak": 0.5}, usable)["Weak"] is None

    strong_hit = rng.uniform(size=n) < 0.70
    tiers2 = tiers.assign(strength="Strong", p_cal=np.where(strong_hit == (label == 1), 0.6, 0.4))
    v2 = validate_tiers(tiers2)
    assert v2["Strong"]["validated"] and v2["Weak"]["validated"]  # cumulative: Strong signals count for Weak too
    cuts = {"Strong": 0.6, "Good": 0.56, "Moderate": 0.53, "Weak": 0.5}
    assert served_cuts(cuts, {"usability": {"usable": True}, "tier_validation": v2}) == cuts
    assert all(c is None for c in served_cuts(cuts, {"usability": {"usable": False}, "tier_validation": v2}).values())

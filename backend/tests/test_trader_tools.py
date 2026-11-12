"""Pure trader-protection logic: position sizing, ATR levels + base rate, scenario coverage, conditions, exits."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from app.services.analysis import conditions as cond
from app.services.analysis.exit_advisor import advise
from app.services.analysis.levels import base_rate, compute_levels
from app.services.analysis.scenario import bands
from app.services.news.guard import GuardResult
from app.services.risk.calculator import RiskInputError, SizeInput, Spec, floor_step, position_size

EURUSD = Spec("EUR/USD", "fx", "EUR", "USD", 100000.0, 5)
USDJPY = Spec("USD/JPY", "fx", "USD", "JPY", 100000.0, 3)
XAUUSD = Spec("XAU/USD", "metal", "XAU", "USD", 100.0, 2)
BTC = Spec("BTC/USDT", "crypto", "BTC", "USDT", None, 2)
CLEAR = GuardResult("clear", ["no relevant high/medium-impact event nearby"])


def size(spec: Spec, entry: float, stop: float, tp: float | None = None, **kw: object):  # type: ignore[no-untyped-def]
    args = {"balance": 10_000.0, "risk_pct": 1.0, "risk_amount": None, "quote_to_account": 1.0} | kw
    return position_size(spec, SizeInput(entry, stop, tp, **args))  # type: ignore[arg-type]


# ---- position size -------------------------------------------------------------------------------------------

def test_fx_position_size_matches_hand_calculation() -> None:
    r = size(EURUSD, 1.1000, 1.0950, 1.1100)  # 50 pips, 1% of 10k = 100 USD
    assert r.side == "long" and r.lots == 0.2 and r.units == pytest.approx(20000)
    assert r.stop_pips == pytest.approx(50) and r.pip_value_per_lot == pytest.approx(10.0)
    assert r.risk_amount == pytest.approx(100.0) and r.risk_pct == pytest.approx(1.0)
    assert r.risk_reward == pytest.approx(2.0) and r.reward_amount == pytest.approx(200.0)
    assert r.warnings == []


def test_jpy_quote_converts_to_account_currency() -> None:
    r = size(USDJPY, 150.00, 150.50, 149.00, quote_to_account=1 / 150)  # short, 50 pips
    assert r.side == "short" and r.lots == 0.3
    assert r.pip_value_per_lot == pytest.approx(1000 / 150)
    assert r.risk_amount == pytest.approx(0.3 * 100000 * 0.5 / 150)


def test_gold_and_crypto_sizes() -> None:
    gold = size(XAUUSD, 2000.0, 1990.0)
    assert gold.lots == 0.1 and gold.units == pytest.approx(10) and gold.stop_pips is None
    btc = size(BTC, 60000.0, 59000.0, size_step=0.001)
    assert btc.lots is None and btc.units == pytest.approx(0.1) and btc.risk_amount == pytest.approx(100.0)


def test_sizes_round_down_never_exceeding_requested_risk() -> None:
    for stop in (1.0967, 1.0933, 1.0901, 1.0999):
        r = size(EURUSD, 1.1000, stop)
        assert r.risk_amount <= 100.0 + 1e-9
    r = size(EURUSD, 1.1000, 1.0967)  # 33 pips -> 0.303 lots -> 0.30
    assert r.lots == 0.3 and r.risk_amount == pytest.approx(99.0)
    assert floor_step(0.1 + 0.2, 0.1) == 0.3 and floor_step(0.3, 0.01) == 0.3  # float noise is not floored away
    assert floor_step(0.29999, 0.01) == 0.29


def test_too_small_risk_warns_instead_of_sizing_up() -> None:
    r = size(EURUSD, 1.1000, 1.0900, risk_amount=1.0)
    assert r.lots == 0 and r.units == 0 and r.risk_amount == 0
    assert "minimum size" in r.warnings[0]


def test_warnings() -> None:
    joined = " | ".join(size(EURUSD, 1.1, 1.0950, 1.1025, risk_pct=6.0, atr=0.02, leverage=10.0,
                             daily_loss_left=50.0).warnings)
    assert "6.0% of the account" in joined
    assert "reward:risk is 0.50" in joined
    assert "0.25 x ATR" in joined
    assert "exceeds the balance" in joined
    assert "only 50.00 is left" in joined
    assert "above the common 1-2%" in " ".join(size(EURUSD, 1.1, 1.0950, risk_pct=3.0).warnings)


def test_invalid_inputs() -> None:
    with pytest.raises(RiskInputError, match="differ"):
        size(EURUSD, 1.1, 1.1)
    with pytest.raises(RiskInputError, match="take_profit must be above"):
        size(EURUSD, 1.1, 1.09, 1.08)
    with pytest.raises(RiskInputError, match="risk_amount"):
        size(EURUSD, 1.1, 1.09, balance=None)


# ---- candles ---------------------------------------------------------------------------------------------------

T0 = int(datetime(2026, 11, 2, tzinfo=UTC).timestamp())  # Monday


def walk(n: int, drift: float = 0.0, vol: float = 0.001, seed: int = 1, tf: int = 900, start: float = 1.1,
         t0: int = T0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = start * np.exp(np.cumsum(rng.normal(drift, vol, n)))
    open_ = np.r_[start, close[:-1]]
    wick = np.abs(rng.normal(0, vol / 2, n)) * close
    return pd.DataFrame({"time": t0 + tf * np.arange(n), "open": open_, "high": np.maximum(open_, close) + wick,
                         "low": np.minimum(open_, close) - wick, "close": close, "volume": 1.0})


def test_levels_geometry() -> None:
    lv = compute_levels(1.1, 0.002, "long", 1.5, (1.0, 2.0))
    assert lv.stop == pytest.approx(1.097) and [p for _, p in lv.targets] == pytest.approx([1.103, 1.106])
    sh = compute_levels(1.1, 0.002, "short", 1.5, (2.0,))
    assert sh.stop == pytest.approx(1.103) and sh.targets[0][1] == pytest.approx(1.094)


def test_base_rate_on_a_random_walk_is_near_the_break_even_rate() -> None:
    c = walk(3000, seed=7)
    one = base_rate(c, "long", 1.5, 1.0, n_entries=2000)
    two = base_rate(c, "long", 1.5, 2.0, n_entries=2000)
    assert one["hit_rate"] == pytest.approx(0.5, abs=0.08)
    assert two["hit_rate"] == pytest.approx(1 / 3, abs=0.08)
    assert one["break_even_hit_rate"] == 0.5 and two["break_even_hit_rate"] == pytest.approx(0.3333, abs=1e-4)
    assert one["entries"] == one["target_first"] + one["stop_first"] + one["neither_within_max_bars"]
    up = walk(3000, drift=0.0008, seed=7)
    assert base_rate(up, "long", 1.5, 1.0)["hit_rate"] > 0.65 > base_rate(up, "short", 1.5, 1.0)["hit_rate"]


def test_base_rate_counts_a_candle_touching_both_levels_as_a_loss() -> None:
    n = 80
    c = pd.DataFrame({"time": T0 + 900 * np.arange(n), "open": 1.0, "high": 1.001, "low": 0.999, "close": 1.0,
                      "volume": 1.0})
    c.loc[n - 1, ["high", "low"]] = [1.5, 0.5]  # one huge candle hits both sides
    r = base_rate(c, "long", 1.5, 1.0, max_bars=50, n_entries=10)
    assert r["target_first"] == 0 and r["stop_first"] >= 1


def test_scenario_band_coverage_is_measured_out_of_sample() -> None:
    c = walk(1400, seed=3)
    out = bands(c, steps=5, window=1000, test=250)
    assert [b["k"] for b in out] == [1, 2, 3, 4, 5]
    widths = [b["high"] - b["low"] for b in out]
    assert widths == sorted(widths)  # uncertainty grows with the horizon
    for b in out:
        assert b["low"] < float(c["close"].iloc[-1]) < b["high"]
        assert b["coverage_tested"] == 250 and b["coverage"] == pytest.approx(0.8, abs=0.08)


def test_scenario_coverage_drops_when_volatility_jumps() -> None:
    calm, wild = walk(1150, seed=4, vol=0.0005), walk(250, seed=5, vol=0.003, t0=T0 + 1150 * 900)
    wild[["open", "high", "low", "close"]] *= float(calm["close"].iloc[-1]) / float(wild["open"].iloc[0])
    out = bands(pd.concat([calm, wild], ignore_index=True), steps=1)
    assert out[0]["coverage"] < 0.6  # an honest coverage figure exposes the miscalibrated band


# ---- conditions ------------------------------------------------------------------------------------------------

def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC)


def series_ending(now: datetime, n: int = 600, seed: int = 3, **kw: object) -> pd.DataFrame:
    """Seed 3: the last candle's volatility is 'normal' (27th percentile)."""
    last_open = int(now.timestamp()) // 900 * 900 - 900
    return walk(n, t0=last_open - 900 * (n - 1), seed=seed, **kw)  # type: ignore[arg-type]


def test_conditions_green_in_london_new_york_overlap() -> None:
    now = at(4, 14, 5)  # Wednesday 14:05 UTC
    c = cond.assess(series_ending(now), "15m", "fx_24x5", now, CLEAR)
    assert c.sessions == ["London", "New York"]
    assert c.light == "green", [f.as_dict() for f in c.factors]
    assert {f.name for f in c.factors} == {"market", "data", "trend", "volatility", "session", "news"}


def test_conditions_red_and_amber_rules() -> None:
    sat = at(7, 12)
    assert cond.assess(series_ending(sat), "15m", "fx_24x5", sat, CLEAR).light == "red"  # market closed
    assert cond.assess(series_ending(sat), "15m", "crypto_24x7", sat, CLEAR).light == "green"
    now = at(4, 14, 5)
    old = series_ending(now - timedelta(hours=2))
    assert cond.assess(old, "15m", "fx_24x5", now, CLEAR).light == "red"  # stale data
    assert cond.assess(series_ending(now), "15m", "fx_24x5", now, GuardResult("blackout", ["CPI"])).light == "red"
    assert cond.assess(series_ending(now), "15m", "fx_24x5", now, GuardResult("unknown", ["x"])).light == "amber"
    rollover = at(4, 22, 5)  # 17:05 New York (EST)
    c = cond.assess(series_ending(rollover), "15m", "fx_24x5", rollover, CLEAR)
    assert c.light == "amber" and "rollover" in next(f.detail for f in c.factors if f.name == "session")


def test_conditions_trend_and_volatility_regimes() -> None:
    now = at(4, 14, 5)
    trend = cond.assess(series_ending(now, drift=0.002, vol=0.001), "15m", "fx_24x5", now, CLEAR)
    assert trend.trend["regime"] == "trending" and trend.trend["direction"] == "up"
    spiky = series_ending(now)
    spiky.loc[len(spiky) - 1, "high"] = spiky["close"].iloc[-1] * 1.05
    v = cond.assess(spiky, "15m", "fx_24x5", now, CLEAR)
    assert v.volatility["regime"] == "extreme" and v.light == "red"


# ---- exit advisor ----------------------------------------------------------------------------------------------

def flat_then(prices: list[float], n: int = 60) -> pd.DataFrame:
    close = np.r_[np.full(n, 1.1), prices]
    open_ = np.r_[close[0], close[:-1]]
    return pd.DataFrame({"time": T0 + 900 * np.arange(len(close)), "open": open_,
                         "high": np.maximum(open_, close) + 0.0002, "low": np.minimum(open_, close) - 0.0002,
                         "close": close, "volume": 1.0})


def sig(direction: str, edge: bool, strength: str = "Good") -> dict:
    return {"direction": direction, "strength": strength, "confidence": 0.6, "timeframe": "15m",
            "model": {"has_demonstrated_edge": edge}}


def test_exit_advice_rules() -> None:
    up = flat_then(list(np.linspace(1.1, 1.13, 30)))
    entry_t = int(up["time"].iloc[60])
    a = advise(up, "long", 1.1, 1.09, None, entry_t, CLEAR, None)
    assert a["r_multiple"] == pytest.approx(3.0, abs=0.05)
    assert a["action"] == "take_partial"
    assert a["suggested_stop"] is not None and a["suggested_stop"] > 1.1

    stopped = flat_then([1.1, 1.095, 1.085, 1.087])
    s = advise(stopped, "long", 1.1, 1.09, None, int(stopped["time"].iloc[60]), CLEAR, None)
    assert s["action"] == "consider_exit" and "traded through your stop" in s["reasons"][0]

    calm = flat_then([1.1005, 1.1008])
    assert advise(calm, "long", 1.1, 1.095, 1.12, int(calm["time"].iloc[60]), CLEAR, None)["action"] == "hold"
    news = advise(calm, "long", 1.1, 1.095, 1.12, None, GuardResult("blackout", ["CPI in 5 min"]), None)
    assert news["action"] == "consider_exit" and "news" in news["reasons"][0]


def test_exit_advice_ignores_signals_without_edge() -> None:
    calm = flat_then([1.1005, 1.1008])
    ignored = advise(calm, "long", 1.1, 1.095, None, None, CLEAR, sig("down", edge=False))
    assert ignored["action"] == "hold" and "ignored" in ignored["notes"][0]
    used = advise(calm, "long", 1.1, 1.095, None, None, CLEAR, sig("down", edge=True))
    assert used["action"] == "consider_exit" and "signal points down" in used["reasons"][0]
    weak = advise(calm, "long", 1.1, 1.095, None, None, CLEAR, sig("down", edge=True, strength="Very Weak - Wait"))
    assert weak["action"] == "hold"

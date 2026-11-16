"""Technical Pattern Projection: pattern rules, base rates against a planted effect, projection shape, fallbacks."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.services.analysis.patterns import LABEL, PATTERNS, classify, outlook

T0 = 1_762_128_000


def frame(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    return pd.DataFrame([{"time": T0 + i * 900, "open": o, "high": h, "low": low, "close": c, "volume": 0.0}
                         for i, (o, h, low, c) in enumerate(rows)])


def plain(n: int, seed: int = 1, start: float = 1.1) -> list[tuple[float, float, float, float]]:
    """Random candles with solid bodies and short wicks: no doji, pin bar or engulfing."""
    rng = np.random.default_rng(seed)
    rows, c = [], start
    for _ in range(n):
        o = c
        c = o + float(rng.choice([-1, 1])) * (abs(rng.normal(0, 0.001)) + 0.0005)
        rows.append((o, max(o, c) + 0.0002, min(o, c) - 0.0002, c))
    return rows


def hammer(prev_close: float) -> tuple[float, float, float, float]:
    o = prev_close
    c = o + 0.0005
    return (o, c + 0.00005, o - 0.003, c)


def test_pattern_rules() -> None:
    soldiers = [(1.00, 1.055, 0.995, 1.05), (1.04, 1.095, 1.035, 1.09), (1.08, 1.135, 1.075, 1.13)]
    crows = [(1.13, 1.135, 1.075, 1.08), (1.09, 1.095, 1.035, 1.04), (1.05, 1.055, 0.995, 1.00)]
    engulf = [(1.05, 1.055, 1.015, 1.02), (1.01, 1.075, 1.005, 1.07)]
    pin = [hammer(1.05)]
    doji = [(1.05, 1.07, 1.03, 1.0505)]
    assert classify(frame(soldiers))[-1] == "three_white_soldiers"
    assert classify(frame(crows))[-1] == "three_black_crows"
    assert classify(frame(engulf))[-1] == "bullish_engulfing"
    assert classify(frame(pin))[-1] == "hammer"
    assert classify(frame(doji))[-1] == "doji"
    assert classify(frame(plain(5)[:1]))[-1] == ""
    assert PATTERNS["hammer"].bias == 1 and PATTERNS["doji"].bias == 0 and "Projection" in LABEL


def planted(effect: bool, n: int = 2400, every: int = 40) -> pd.DataFrame:
    """Hammers every ``every`` candles; with ``effect`` the five candles after each one rise."""
    rows = plain(n, seed=7)
    rng = np.random.default_rng(3)
    out: list[tuple[float, float, float, float]] = []
    i = 0
    while i < n:
        prev = out[-1][3] if out else 1.1
        if i % every == every - 1 or i == n - 1:
            out.append(hammer(prev))
            i += 1
            for _ in range(5 if i < n - 1 else 0):
                o = out[-1][3]
                step = 0.002 if effect else float(rng.choice([-1, 1])) * 0.002
                c = o + step
                out.append((o, max(o, c) + 0.0002, min(o, c) - 0.0002, c))
                i += 1
            continue
        o, h, low, c = rows[i]
        shift = prev - o
        out.append((o + shift, h + shift, low + shift, c + shift))
        i += 1
    return frame(out[:n])


def test_a_real_effect_is_measured_and_projected_upward() -> None:
    res = outlook(planted(effect=True), steps=5)
    assert res["pattern"]["key"] == "hammer" and res["pattern"]["enough_cases"]
    br = res["base_rate"]
    assert br["cases"] >= 30 and br["rate"] > 0.95 and br["edge"] is True
    assert br["ci95"][0] > br["baseline"]
    proj = res["projection"]
    assert proj["basis"] == "pattern" and len(proj["steps"]) == 5
    closes = [s["close"] for s in proj["steps"]]
    assert closes == sorted(closes) and closes[0] > res["last_close"]
    for s in proj["steps"]:
        assert s["low"] <= min(s["open"], s["close"]) and s["high"] >= max(s["open"], s["close"])
        assert s["band_low"] <= s["close"] <= s["band_high"]


def test_no_effect_means_no_edge() -> None:
    res = outlook(planted(effect=False), steps=5)
    assert res["pattern"]["key"] == "hammer"
    assert res["base_rate"]["edge"] is False


def test_too_few_cases_fall_back_to_the_typical_range() -> None:
    rows = plain(600, seed=11)
    rows.append(hammer(rows[-1][3]))
    res = outlook(frame(rows), steps=3)
    assert res["pattern"]["key"] == "hammer" and res["pattern"]["enough_cases"] is False
    assert res["projection"]["basis"] == "all_candles" and len(res["projection"]["steps"]) == 3
    assert res["pattern"]["past_cases"] == 0 and res["base_rate"] is None  # nothing to measure


def test_no_pattern_and_structure() -> None:
    rows = plain(400, seed=5)
    res = outlook(frame(rows), steps=5)
    if res["pattern"] is None:  # three plain green candles in a row would be soldiers
        assert res["base_rate"] is None
    assert res["projection"]["basis"] in ("all_candles", "pattern")
    st = res["structure"]
    assert st["swing"] in ("uptrend", "downtrend", "range") and st["lookback"] == 20
    assert 0 <= st["rsi"] <= 100 and st["momentum_pct"] is not None

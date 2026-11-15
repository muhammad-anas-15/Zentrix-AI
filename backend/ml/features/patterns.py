"""Rule-based candlestick pattern detector.

``detect_pattern`` (scalar) is the reference definition; ``detect_patterns`` is the vectorised version
used for features and must agree with it (covered by tests). The vocabulary is fixed so the one-hot
feature columns are identical in training and inference.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Order matters: the first matching rule wins.
PATTERNS: tuple[str, ...] = (
    "Doji",
    "Hammer",
    "Shooting Star",
    "Bullish Engulfing",
    "Bearish Engulfing",
    "Bullish Candle",
    "Bearish Candle",
)

PATTERN_INFO: dict[str, tuple[str, str]] = {
    "Doji": ("Indecision between buyers and sellers.",
             "Wait for the next candle to confirm direction before entering."),
    "Hammer": ("Sellers pushed price down but buyers pulled it back up.",
               "Often signals bullish reversal, especially after a downtrend."),
    "Shooting Star": ("Buyers pushed price up but sellers took control.",
                      "Often signals bearish reversal, especially after an uptrend."),
    "Bullish Engulfing": ("Strong green candle fully covers the prior red candle.",
                          "Often read as a bullish reversal signal; needs confirmation."),
    "Bearish Engulfing": ("Strong red candle fully covers the prior green candle.",
                          "Often read as a bearish reversal signal; needs confirmation."),
    "Bullish Candle": ("Buyers in control this period.", "Weak on its own; read it with trend context."),
    "Bearish Candle": ("Sellers in control this period.", "Weak on its own; read it with trend context."),
}

# Floor for a zero-range candle. The old code used an absolute 0.0001, which is one pip on EUR/USD but
# meaningless on gold or BTC; a scale-free epsilon keeps the rule identical across instruments.
_EPS = 1e-12


def detect_pattern(o: float, h: float, low: float, c: float, prev_o: float, prev_c: float) -> str:
    body = abs(c - o)
    range_ = max(h - low, _EPS)
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - low
    if body / range_ < 0.1:
        return "Doji"
    if lower_wick > body * 2 and upper_wick < body:
        return "Hammer"
    if upper_wick > body * 2 and lower_wick < body:
        return "Shooting Star"
    if c > o and prev_c < prev_o and c > prev_o and o < prev_c:
        return "Bullish Engulfing"
    if c < o and prev_c > prev_o and c < prev_o and o > prev_c:
        return "Bearish Engulfing"
    if c > o:
        return "Bullish Candle"
    return "Bearish Candle"


def detect_patterns(candles: pd.DataFrame) -> pd.Series:
    """Pattern name per row. The first row is compared with itself (no previous candle)."""
    o, h, low, c = (candles[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    po = candles["open"].shift(1).fillna(candles["open"]).to_numpy(dtype=float)
    pc = candles["close"].shift(1).fillna(candles["close"]).to_numpy(dtype=float)
    body = np.abs(c - o)
    range_ = np.maximum(h - low, _EPS)
    upper = h - np.maximum(o, c)
    lower = np.minimum(o, c) - low
    conditions = [
        body / range_ < 0.1,
        (lower > body * 2) & (upper < body),
        (upper > body * 2) & (lower < body),
        (c > o) & (pc < po) & (c > po) & (o < pc),
        (c < o) & (pc > po) & (c < po) & (o > pc),
        c > o,
    ]
    names = np.select(conditions, list(PATTERNS[:-1]), default=PATTERNS[-1])
    return pd.Series(names, index=candles.index, name="pattern")

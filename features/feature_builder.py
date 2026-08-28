"""
Combines indicators + patterns + support/resistance into a single
feature set for the latest candle. This is the shared input used by
both the ML model (Phase 2) and the reasoning/orchestrator layer.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from features.indicators import rsi, ema, macd, atr, bollinger_bands, volume_change
from features.patterns import detect_patterns_series
from features.support_resistance import calc_support_resistance


def build_features(candles: list) -> dict:
    """
    candles: list of dicts [{time, open, high, low, close, volume}, ...]
             chronological order, at least 30 candles recommended.
    Returns a single dict of computed features for the latest candle.
    """
    if len(candles) < 20:
        raise ValueError("Need at least 20 candles to compute reliable indicators")

    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    volumes = [c.get("volume", 0) for c in candles]

    rsi_val = rsi(closes)
    ema20 = ema(closes, 20)
    ema50 = ema(closes, 50) if len(closes) >= 50 else ema(closes, len(closes) - 1)
    macd_line, macd_signal = macd(closes)
    atr_val = atr(highs, lows, closes)
    bb_upper, bb_mid, bb_lower = bollinger_bands(closes)
    vol_change = volume_change(volumes)

    resistance, support = calc_support_resistance(candles)
    patterned = detect_patterns_series(candles)
    latest_pattern = patterned[-1]

    current_price = closes[-1]

    return {
        "current_price": current_price,          # kept for reference/backtest only — NOT fed to ML
        "rsi": rsi_val,
        "price_vs_ema20_pct": round((current_price - ema20) / ema20 * 100, 4),
        "price_vs_ema50_pct": round((current_price - ema50) / ema50 * 100, 4),
        "ema20_vs_ema50_pct": round((ema20 - ema50) / ema50 * 100, 4),
        "macd_norm": round(macd_line / current_price * 100, 6),
        "macd_signal_norm": round(macd_signal / current_price * 100, 6),
        "macd_hist_norm": round((macd_line - macd_signal) / current_price * 100, 6),
        "atr_pct": round(atr_val / current_price * 100, 4),
        "price_vs_bollinger_upper_pct": round((current_price - bb_upper) / current_price * 100, 4),
        "price_vs_bollinger_lower_pct": round((current_price - bb_lower) / current_price * 100, 4),
        "bollinger_width_pct": round((bb_upper - bb_lower) / bb_mid * 100, 4),
        "volume_change_pct": vol_change,
        "price_vs_resistance_pct": round((current_price - resistance) / current_price * 100, 4),
        "price_vs_support_pct": round((current_price - support) / current_price * 100, 4),
        "resistance": resistance,   # reference only, not ML input
        "support": support,         # reference only, not ML input
        "pattern": latest_pattern["pattern"],
        "pattern_context": latest_pattern["context"],
        "pattern_book_rule": latest_pattern["book_rule"],
        "candles_with_patterns": patterned,
    }


if __name__ == "__main__":
    import random
    demo_candles = []
    price = 100
    for i in range(40):
        o = price
        c = price + random.uniform(-1, 1)
        h = max(o, c) + random.uniform(0, 0.5)
        l = min(o, c) - random.uniform(0, 0.5)
        demo_candles.append({"time": i, "open": o, "high": h, "low": l, "close": c, "volume": random.uniform(100, 500)})
        price = c

    features = build_features(demo_candles)
    for k, v in features.items():
        if k != "candles_with_patterns":
            print(f"{k}: {v}")
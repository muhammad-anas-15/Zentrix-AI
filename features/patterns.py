"""
Rule-based candlestick pattern detector. Each function checks one
candle (using open/high/low/close of current + previous candle)
and returns (pattern_name, context, book_rule) or None if no match.
"""


def detect_pattern(o, h, l, c, prev_o, prev_c):
    body = abs(c - o)
    range_ = max(h - l, 0.0001)
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l

    if body / range_ < 0.1:
        return ("Doji", "Indecision between buyers and sellers.",
                "Wait for the next candle to confirm direction before entering.")

    if lower_wick > body * 2 and upper_wick < body:
        return ("Hammer", "Sellers pushed price down but buyers pulled it back up.",
                "Often signals bullish reversal, especially after a downtrend.")

    if upper_wick > body * 2 and lower_wick < body:
        return ("Shooting Star", "Buyers pushed price up but sellers took control.",
                "Often signals bearish reversal, especially after an uptrend.")

    if c > o and prev_c < prev_o and c > prev_o and o < prev_c:
        return ("Bullish Engulfing", "Strong green candle fully covers the prior red candle.",
                "High-probability bullish reversal signal.")

    if c < o and prev_c > prev_o and c < prev_o and o > prev_c:
        return ("Bearish Engulfing", "Strong red candle fully covers the prior green candle.",
                "High-probability bearish reversal signal.")

    if c > o:
        return ("Bullish Candle", "Buyers in control this period.",
                "Momentum favors continuation upward.")

    return ("Bearish Candle", "Sellers in control this period.",
            "Momentum favors continuation downward.")


def detect_patterns_series(candles: list) -> list:
    """
    candles: list of dicts with open/high/low/close (chronological order)
    Returns same list with pattern/context/book_rule added to each candle.
    """
    result = []
    for i, c in enumerate(candles):
        prev = candles[i - 1] if i > 0 else c
        pattern, context, rule = detect_pattern(
            c["open"], c["high"], c["low"], c["close"], prev["open"], prev["close"]
        )
        result.append({**c, "pattern": pattern, "context": context, "book_rule": rule})
    return result


if __name__ == "__main__":
    sample = [
        {"open": 100, "high": 105, "low": 98, "close": 99},
        {"open": 99, "high": 108, "low": 97, "close": 107},
    ]
    for row in detect_patterns_series(sample):
        print(row["pattern"], "-", row["book_rule"])
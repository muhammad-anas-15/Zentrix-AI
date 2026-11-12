"""
Simple support/resistance detection using recent swing highs/lows
(pivot points). No ML needed — pure price-action math.
"""


def calc_support_resistance(candles: list, lookback: int = 20):
    """
    candles: list of dicts with high/low (chronological order)
    Returns (resistance, support) as the max high / min low over lookback window.
    """
    window = candles[-lookback:] if len(candles) >= lookback else candles
    highs = [c["high"] for c in window]
    lows = [c["low"] for c in window]
    return max(highs), min(lows)


def find_pivot_points(candles: list, left: int = 3, right: int = 3):
    """
    Detects local swing highs/lows (a candle whose high/low is the
    extreme among `left` candles before and `right` candles after it).
    Returns list of {index, type: 'high'|'low', price}.
    """
    pivots = []
    for i in range(left, len(candles) - right):
        window = candles[i - left:i + right + 1]
        high_vals = [c["high"] for c in window]
        low_vals = [c["low"] for c in window]

        if candles[i]["high"] == max(high_vals):
            pivots.append({"index": i, "type": "high", "price": candles[i]["high"]})
        if candles[i]["low"] == min(low_vals):
            pivots.append({"index": i, "type": "low", "price": candles[i]["low"]})
    return pivots


if __name__ == "__main__":
    sample = [{"high": 100 + i % 5, "low": 95 + i % 3} for i in range(30)]
    r, s = calc_support_resistance(sample)
    print("Resistance:", r, "Support:", s)
    print("Pivots:", find_pivot_points(sample)[:3])
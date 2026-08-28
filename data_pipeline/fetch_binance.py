"""
Fetches OHLCV candle data from Binance public API (no API key needed for
market data). Works for spot pairs like BTCUSDT, ETHUSDT.
"""
import time
import requests

BINANCE_BASE_URL = "https://fapi.binance.com/fapi/v1/klines"  # Futures/Perp — matches Binance app's default view

INTERVAL_MS = {
    "1m": 60_000, "5m": 300_000, "15m": 900_000,
    "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000,
}


def fetch_binance_ohlcv(symbol: str, interval: str = "15m", limit: int = 1000,
                         end_time_ms: int = None):
    """Single API call — max 1000 candles. Use fetch_binance_history() for more."""
    params = {"symbol": symbol.upper(), "interval": interval, "limit": limit}
    if end_time_ms:
        params["endTime"] = end_time_ms
    resp = requests.get(BINANCE_BASE_URL, params=params, timeout=10)
    resp.raise_for_status()
    raw = resp.json()

    candles = []
    for row in raw:
        candles.append({
            "time": int(row[0] // 1000),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5]),
        })
    return candles


def fetch_binance_history(symbol: str, interval: str = "1h", months: int = 6):
    """
    Paginated fetch to get MONTHS of history, bypassing the 1000-candle
    single-call limit. Loops backward in time using endTime until enough
    candles are collected. Respects Binance rate limits with small delays.
    """
    if interval not in INTERVAL_MS:
        raise ValueError(f"Unsupported interval: {interval}")

    ms_per_candle = INTERVAL_MS[interval]
    total_ms = months * 30 * 24 * 60 * 60 * 1000
    target_candles = total_ms // ms_per_candle

    all_candles = []
    end_time = None  # None = fetch most recent first

    while len(all_candles) < target_candles:
        batch = fetch_binance_ohlcv(symbol, interval, limit=1000, end_time_ms=end_time)
        if not batch:
            break
        all_candles = batch + all_candles  # prepend older data
        end_time = batch[0]["time"] * 1000 - ms_per_candle  # go further back
        if len(batch) < 1000:  # no more history available
            break
        time.sleep(0.3)  # be nice to Binance rate limits

    # de-duplicate by time and sort chronologically
    seen = {}
    for c in all_candles:
        seen[c["time"]] = c
    return sorted(seen.values(), key=lambda c: c["time"])


if __name__ == "__main__":
    data = fetch_binance_history("BTCUSDT", "1h", months=6)
    print(f"Fetched {len(data)} candles")
    print("Oldest:", data[0])
    print("Newest:", data[-1])
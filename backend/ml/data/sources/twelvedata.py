"""
Fetches OHLCV candle data for forex pairs using Twelve Data API.
Free tier: 800 requests/day, 15-min delayed on some plans.
Sign up free key at https://twelvedata.com
"""
import os
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

TWELVE_DATA_URL = "https://api.twelvedata.com/time_series"
API_KEY = os.getenv("TWELVE_DATA_API_KEY", "")


def fetch_forex_ohlcv(symbol: str, interval: str = "15min", outputsize: int = 100):
    """
    symbol: e.g. 'EUR/USD'
    interval: '1min', '5min', '15min', '1h'
    Returns list of dicts: [{time, open, high, low, close, volume}, ...]
    """
    if not API_KEY:
        raise ValueError("TWELVE_DATA_API_KEY not set in environment")

    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": API_KEY,
        "format": "JSON",
    }
    resp = requests.get(TWELVE_DATA_URL, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    if "values" not in data:
        raise RuntimeError(f"Forex fetch failed: {data.get('message', data)}")

    candles = []
    for row in reversed(data["values"]):  # API returns newest first
        dt = datetime.strptime(row["datetime"], "%Y-%m-%d %H:%M:%S") \
            if len(row["datetime"]) > 10 else datetime.strptime(row["datetime"], "%Y-%m-%d")
        candles.append({
            "time": int(dt.timestamp()),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row.get("volume", 0) or 0),
        })
    return candles


if __name__ == "__main__":
    data = fetch_forex_ohlcv("EUR/USD", "15min", 10)
    for c in data[-3:]:
        print(c)
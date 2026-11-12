"""Twelve Data time series (forex and gold).

- Timestamps are requested in UTC (``timezone=UTC``) and parsed as UTC. The old code parsed naive
  datetimes with the machine's local timezone, which shifted every candle on a non-UTC machine.
- Free plan: 8 requests/minute, <=5000 candles per call. ``fetch_range`` pages backwards with
  ``end_date`` to get more history than one call allows.
- The API key comes from the environment only (TWELVE_DATA_API_KEY).
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

import pandas as pd
import requests

from ml.data.candles import interval_seconds, to_frame
from ml.settings import get_settings

log = logging.getLogger(__name__)

BASE_URL = "https://api.twelvedata.com/time_series"
MAX_OUTPUTSIZE = 5000
TD_INTERVALS = {"1m": "1min", "5m": "5min", "15m": "15min", "1h": "1h", "4h": "4h", "1d": "1day"}

_last_call = 0.0


class TwelveDataError(RuntimeError):
    pass


def _throttle() -> None:
    global _last_call
    wait = get_settings().twelve_data_min_interval_s - (time.monotonic() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.monotonic()


def parse_datetime(value: str) -> int:
    fmt = "%Y-%m-%d %H:%M:%S" if len(value) > 10 else "%Y-%m-%d"
    return int(datetime.strptime(value, fmt).replace(tzinfo=UTC).timestamp())


def format_datetime(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d %H:%M:%S")


def parse_values(values: list[dict]) -> list[dict]:
    return [
        {"time": parse_datetime(v["datetime"]), "open": float(v["open"]), "high": float(v["high"]),
         "low": float(v["low"]), "close": float(v["close"]), "volume": float(v.get("volume") or 0)}
        for v in values
    ]


def fetch_time_series(symbol: str, interval: str, outputsize: int = 100, end_ts: int | None = None,
                      session: requests.Session | None = None, max_retries: int = 3) -> list[dict]:
    """One API call (throttled). Returns candles ascending; [] when the provider has no data."""
    key = get_settings().twelve_data_api_key.get_secret_value()
    if not key:
        raise TwelveDataError("TWELVE_DATA_API_KEY is not set (see backend/.env.example)")
    interval_seconds(interval)
    params: dict[str, str | int] = {
        "symbol": symbol, "interval": TD_INTERVALS[interval], "outputsize": min(outputsize, MAX_OUTPUTSIZE),
        "timezone": "UTC", "format": "JSON", "apikey": key,
    }
    if end_ts is not None:
        params["end_date"] = format_datetime(end_ts)

    for attempt in range(max_retries + 1):
        _throttle()
        resp = (session or requests).get(BASE_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if "values" in data:
            return parse_values(list(reversed(data["values"])))  # API is newest-first
        message = str(data.get("message", data))
        if "no data is available" in message.lower():
            return []
        if data.get("code") == 429 and attempt < max_retries:
            log.warning("Twelve Data rate limit hit; sleeping 65s")
            time.sleep(65)
            continue
        # Never echo the request (it contains the key); the message alone is safe.
        raise TwelveDataError(f"Twelve Data error for {symbol} {interval}: {message}")
    raise TwelveDataError("unreachable")


def fetch_latest(symbol: str, interval: str, limit: int, session: requests.Session | None = None) -> pd.DataFrame:
    """Most recent ``limit`` candles (the last one may still be forming)."""
    return to_frame(fetch_time_series(symbol, interval, outputsize=limit, session=session))


def fetch_range(symbol: str, interval: str, start_ts: int, end_ts: int | None = None,
                session: requests.Session | None = None) -> pd.DataFrame:
    """All candles with open time in [start_ts, end_ts], paging backwards with end_date."""
    rows: list[dict] = []
    cursor = end_ts
    while True:
        batch = fetch_time_series(symbol, interval, outputsize=MAX_OUTPUTSIZE, end_ts=cursor, session=session)
        if not batch:
            break
        oldest = batch[0]["time"]
        if cursor is not None and oldest >= cursor:  # no progress (end_date is inclusive)
            break
        rows.extend(batch)
        if oldest <= start_ts or len(batch) < MAX_OUTPUTSIZE:
            break
        cursor = oldest
    df = to_frame(rows)
    mask = df["time"] >= start_ts
    if end_ts is not None:
        mask &= df["time"] <= end_ts
    return df[mask].reset_index(drop=True)

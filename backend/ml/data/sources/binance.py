"""Binance klines (public market data, no key): USD-M futures (``market="usdm"``, default, used for training)
and spot (``market="spot"``).

Candle ``time`` is the kline open time in UTC epoch seconds. The newest kline returned by the API is
usually still forming; callers must apply ``drop_unclosed`` before computing signals.
Binance blocks some regions (for example US IPs): host the worker in an allowed region. Spot public data is
also served by ``data-api.binance.vision`` (set BINANCE_SPOT_URL).
"""

from __future__ import annotations

import os
import time
from typing import Literal

import pandas as pd
import requests

from ml.data.candles import interval_seconds, to_frame

Market = Literal["usdm", "spot"]
BASE_URLS: dict[str, str] = {
    "usdm": os.getenv("BINANCE_USDM_URL", "https://fapi.binance.com/fapi/v1/klines"),
    "spot": os.getenv("BINANCE_SPOT_URL", "https://api.binance.com/api/v3/klines"),
}
MAX_LIMIT: dict[str, int] = {"usdm": 1500, "spot": 1000}
PAGE_LIMIT = 1000


def fetch_klines(symbol: str, interval: str, limit: int = PAGE_LIMIT, start_ms: int | None = None,
                 end_ms: int | None = None, session: requests.Session | None = None,
                 market: Market = "usdm") -> list[dict]:
    """One API call. With ``start_ms`` the API returns up to ``limit`` klines ascending from it;
    without it, the most recent ``limit`` klines (ending at ``end_ms`` if given)."""
    interval_seconds(interval)  # validate
    params: dict[str, str | int] = {"symbol": symbol.upper(), "interval": interval,
                                    "limit": min(limit, MAX_LIMIT[market])}
    if start_ms is not None:
        params["startTime"] = start_ms
    if end_ms is not None:
        params["endTime"] = end_ms
    resp = (session or requests).get(BASE_URLS[market], params=params, timeout=15)
    resp.raise_for_status()
    return [
        {"time": int(row[0]) // 1000, "open": float(row[1]), "high": float(row[2]),
         "low": float(row[3]), "close": float(row[4]), "volume": float(row[5])}
        for row in resp.json()
    ]


def fetch_latest(symbol: str, interval: str, limit: int, session: requests.Session | None = None,
                 market: Market = "usdm") -> pd.DataFrame:
    """Most recent ``limit`` klines (the last one may still be forming)."""
    return to_frame(fetch_klines(symbol, interval, limit=limit, session=session, market=market))


def fetch_range(symbol: str, interval: str, start_ts: int, end_ts: int | None = None,
                session: requests.Session | None = None, pause_s: float = 0.25,
                market: Market = "usdm") -> pd.DataFrame:
    """All klines with open time in [start_ts, end_ts], paging forward from start_ts."""
    step = interval_seconds(interval)
    end_ts = int(time.time()) if end_ts is None else end_ts
    rows: list[dict] = []
    cursor = start_ts
    while cursor <= end_ts:
        batch = fetch_klines(symbol, interval, limit=PAGE_LIMIT, start_ms=cursor * 1000,
                             end_ms=end_ts * 1000, session=session, market=market)
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < PAGE_LIMIT:
            break
        cursor = batch[-1]["time"] + step
        time.sleep(pause_s)
    df = to_frame(rows)
    return df[(df["time"] >= start_ts) & (df["time"] <= end_ts)].reset_index(drop=True)

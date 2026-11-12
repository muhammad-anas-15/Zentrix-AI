"""Market hours. Forex and spot gold trade Sunday 17:00 to Friday 17:00 New York time.

The Twelve Data feed also returns candles while the market is closed (about 25% of all candles): tiny ranges,
many flat outcomes and a skew between open and close fields. They are not tradeable prices, so they are removed
before features are computed, identically in training (``load_history``) and live inference (``fetch_recent``).
Crypto trades 24/7 and is left unchanged.
"""

from __future__ import annotations

import pandas as pd

from ml.data.candles import is_forex

NY = "America/New_York"


def market_open_mask(times: pd.Series, symbol: str) -> pd.Series:
    """True for candles whose OPEN time falls inside the trading week (DST handled via New York time)."""
    if not is_forex(symbol):
        return pd.Series(True, index=times.index)
    ny = pd.to_datetime(times, unit="s", utc=True).dt.tz_convert(NY)
    dow, hour = ny.dt.dayofweek, ny.dt.hour
    closed = (dow == 5) | ((dow == 4) & (hour >= 17)) | ((dow == 6) & (hour < 17))
    return ~closed


def trading_hours_only(candles: pd.DataFrame, symbol: str) -> pd.DataFrame:
    return candles.loc[market_open_mask(candles["time"], symbol)].reset_index(drop=True)

"""Market hours by session code (``instruments.session`` in the database).

Forex, spot metals and the commodity references trade Sunday 17:00 to Friday 17:00 New York time. The Twelve
Data feed also returns candles while the market is closed (about 25% of all candles): tiny ranges, many flat
outcomes and a skew between open and close fields. They are not tradeable prices, so they are removed before
features are computed, identically in training, live inference and ingestion. Crypto trades 24/7.

Always pass a session code. ML code that only has a provider symbol uses ``session_for_symbol`` (provider
symbols: "EUR/USD" forex, "BTCUSDT" crypto); never infer a session from canonical DB symbols ("BTC/USDT").
"""

from __future__ import annotations

import pandas as pd

from ml.data.candles import is_forex

NY = "America/New_York"
# Metals/commodities also pause daily 17:00-18:00 New York. That break is not filtered yet so live features
# stay identical to how the current models were trained; add it together with a retrain.
WEEKLY_SESSIONS = frozenset({"fx_24x5", "metals_23x5", "commodities_23x5"})
ALWAYS_OPEN = frozenset({"crypto_24x7"})
SESSIONS = WEEKLY_SESSIONS | ALWAYS_OPEN


def session_for_symbol(provider_symbol: str) -> str:
    """Session for an ML/provider symbol (training data): forex pairs carry a slash, Binance symbols do not."""
    return "fx_24x5" if is_forex(provider_symbol) else "crypto_24x7"


def _check(session: str) -> str:
    if session not in SESSIONS:
        raise ValueError(f"unknown session code {session!r} (known: {sorted(SESSIONS)})")
    return session


def market_open_mask(times: pd.Series, session: str) -> pd.Series:
    """True for candles whose OPEN time (UTC epoch seconds) falls inside the trading week."""
    if _check(session) in ALWAYS_OPEN:
        return pd.Series(True, index=times.index)
    ny = pd.to_datetime(times, unit="s", utc=True).dt.tz_convert(NY)
    dow, hour = ny.dt.dayofweek, ny.dt.hour
    closed = (dow == 5) | ((dow == 4) & (hour >= 17)) | ((dow == 6) & (hour < 17))
    return ~closed


def is_market_open(ts: int, session: str) -> bool:
    return bool(market_open_mask(pd.Series([ts]), session).iloc[0])


def trading_hours_only(candles: pd.DataFrame, session: str) -> pd.DataFrame:
    return candles.loc[market_open_mask(candles["time"], session)].reset_index(drop=True)

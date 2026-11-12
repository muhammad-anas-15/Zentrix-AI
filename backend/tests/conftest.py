from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ml.data.candles import INTERVAL_SECONDS, to_frame

T0 = 1_700_006_400  # 2023-11-15 00:00:00 UTC (aligned to the day)


def make_candles(n: int, interval: str = "15m", seed: int = 0, start: int = T0, price: float = 1.1,
                 decimals: int | None = None) -> pd.DataFrame:
    """Random-walk OHLCV candles (open time UTC epoch seconds)."""
    rng = np.random.default_rng(seed)
    step = INTERVAL_SECONDS[interval]
    close = price * np.exp(np.cumsum(rng.normal(0, 0.001, n)))
    open_ = np.r_[price, close[:-1]]
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.0006, n))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.0006, n))
    df = pd.DataFrame({"time": start + step * np.arange(n), "open": open_, "high": high, "low": low,
                       "close": close, "volume": rng.uniform(100, 500, n)})
    if decimals is not None:
        df[["open", "high", "low", "close"]] = df[["open", "high", "low", "close"]].round(decimals)
    return to_frame(df)


def resample(candles: pd.DataFrame, to_interval: str) -> pd.DataFrame:
    """Aggregate base candles into higher-TF candles (bucketed by open time)."""
    step = INTERVAL_SECONDS[to_interval]
    g = candles.assign(bucket=candles["time"] // step * step).groupby("bucket")
    out = pd.DataFrame({"time": g["time"].first() // step * step, "open": g["open"].first(),
                        "high": g["high"].max(), "low": g["low"].min(), "close": g["close"].last(),
                        "volume": g["volume"].sum()})
    return to_frame(out.reset_index(drop=True))


@pytest.fixture
def base_15m() -> pd.DataFrame:
    return make_candles(1500, "15m", seed=1)


@pytest.fixture
def htf_1h(base_15m: pd.DataFrame) -> pd.DataFrame:
    return resample(base_15m, "1h")

"""Shared loaders for the analysis tools: stored closed candles of an instrument's listing + indicators."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.market import Timeframe
from app.services.marketdata.candles import load_series
from app.services.marketdata.lookup import ListingRef, listing_for
from ml.features.indicators import atr, rolling_support_resistance


@dataclass(frozen=True)
class Series:
    ref: ListingRef
    timeframe: str
    candles: pd.DataFrame  # ML candle frame (time = open, UTC epoch s), ascending, closed candles only

    @property
    def symbol(self) -> str:
        return self.ref.instrument.symbol

    @property
    def decimals(self) -> int:
        return int(self.ref.instrument.price_decimals)


async def load_market(db: AsyncSession, symbol: str, timeframe: str, venue: str | None = None, n: int = 600,
                      min_candles: int = 30) -> Series:
    if await db.scalar(select(Timeframe.code).where(Timeframe.code == timeframe)) is None:
        raise AppError(422, "unknown_timeframe", f"Unknown timeframe {timeframe}")
    ref = await listing_for(db, symbol, venue)
    candles = await load_series(db, ref.listing.id, timeframe, n)
    if len(candles) < min_candles:
        raise AppError(404, "no_data", f"Not enough stored {timeframe} candles for {symbol} "
                                       f"({len(candles)} < {min_candles}); this series is not ingested yet",
                       details={"symbol": symbol, "timeframe": timeframe, "candles": len(candles)})
    return Series(ref, timeframe, candles)


def with_atr(candles: pd.DataFrame, period: int = 14) -> pd.Series:
    return atr(candles["high"], candles["low"], candles["close"], period)


def support_resistance(candles: pd.DataFrame, lookback: int = 20) -> tuple[float, float]:
    """(support, resistance): lowest low / highest high of the last ``lookback`` closed candles."""
    res, sup = rolling_support_resistance(candles["high"], candles["low"], lookback)
    return float(sup.iloc[-1]), float(res.iloc[-1])


def rnd(x: float | None, decimals: int) -> float | None:
    if x is None or not np.isfinite(x):
        return None
    return round(float(x), decimals)

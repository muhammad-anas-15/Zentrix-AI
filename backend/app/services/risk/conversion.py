"""Quote-currency -> account-currency rate from stored prices (direct pair, inverse pair, or via USD).

USDT is treated as 1 USD (stated in the response). The latest *closed* stored candle is used, so a rate can be
up to one candle old; clients may pass their own rate instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market import Instrument, InstrumentListing
from app.services.marketdata.lookup import last_price

ACCOUNT_CURRENCIES = ("USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "NZD", "USDT")


class ConversionUnavailable(LookupError):
    pass


@dataclass
class Rate:
    rate: float
    notes: list[str] = field(default_factory=list)
    as_of: datetime | None = None


def _norm(ccy: str, notes: list[str]) -> str:
    if ccy == "USDT":
        if "USDT treated as 1 USD" not in notes:
            notes.append("USDT treated as 1 USD")
        return "USD"
    return ccy


async def _pair_price(db: AsyncSession, symbol: str, at: datetime | None) -> tuple[float, datetime] | None:
    listing_id = await db.scalar(select(InstrumentListing.id).join(Instrument).where(
        Instrument.symbol == symbol, InstrumentListing.is_primary))
    if listing_id is None:
        return None
    p = await last_price(db, listing_id, at)
    return (p.price, p.as_of) if p else None


async def _direct(db: AsyncSession, src: str, dst: str,
                  at: datetime | None) -> tuple[float, str, datetime | None] | None:
    if src == dst:
        return 1.0, "", None
    if (p := await _pair_price(db, f"{src}/{dst}", at)) is not None:
        return p[0], f"{src}/{dst} {p[0]}", p[1]
    if (p := await _pair_price(db, f"{dst}/{src}", at)) is not None:
        return 1 / p[0], f"1 / {dst}/{src} {p[0]}", p[1]
    return None


async def quote_to_account(db: AsyncSession, quote: str, account: str, at: datetime | None = None) -> Rate:
    notes: list[str] = []
    src, dst = _norm(quote, notes), _norm(account, notes)
    if src == dst:
        return Rate(1.0, notes)
    d = await _direct(db, src, dst, at)
    if d is not None:
        return Rate(d[0], [*notes, f"rate from {d[1]}"], d[2])
    a, b = await _direct(db, src, "USD", at), await _direct(db, "USD", dst, at)
    if a is not None and b is not None:
        times = [x for x in (a[2], b[2]) if x is not None]
        return Rate(a[0] * b[0], [*notes, f"rate via USD from {a[1]} and {b[1]}"], min(times) if times else None)
    raise ConversionUnavailable(f"no stored price to convert {quote} to {account}; pass conversion_rate "
                                f"(1 {quote} in {account})")

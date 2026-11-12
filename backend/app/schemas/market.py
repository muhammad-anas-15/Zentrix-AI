from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class VenueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    name: str
    kind: Literal["exchange", "data_vendor", "broker"]


class TimeframeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    seconds: int


class ListingOut(BaseModel):
    venue: str
    venue_symbol: str
    status: Literal["active", "planned", "restricted", "disabled"]
    is_primary: bool
    note: str | None


class InstrumentOut(BaseModel):
    symbol: str = Field(description="Canonical symbol, e.g. EUR/USD, BTC/USDT, BTC/USDT:PERP")
    display_name: str
    asset_class: Literal["fx", "metal", "commodity", "crypto", "index", "equity"]
    instrument_type: Literal["spot", "perpetual", "future", "cfd"]
    base: str
    quote: str
    settle: str | None
    contract_size: float | None
    price_decimals: int
    session: str
    active: bool = Field(description="False until the instrument has a usable data feed")
    listings: list[ListingOut]


class InstrumentPage(BaseModel):
    items: list[InstrumentOut]
    total: int
    limit: int
    offset: int

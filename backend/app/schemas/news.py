from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.signals import DISCLAIMER

CALENDAR_SOURCE = "ForexFactory weekly calendar (unofficial feed; to be replaced by a licensed calendar)"


class NewsEventOut(BaseModel):
    title: str
    currency: str = Field(description="Calendar country code: USD, EUR, ... or All")
    impact: Literal["high", "medium", "low", "holiday", "none"]
    event_at: datetime
    in_s: int = Field(description="Seconds from now (negative = already happened)")
    forecast: str | None = None
    previous: str | None = None
    actual: str | None = None


class NewsEventsOut(BaseModel):
    items: list[NewsEventOut]
    calendar_updated_at: datetime | None
    source: str = CALENDAR_SOURCE


class GuardOut(BaseModel):
    symbol: str
    state: Literal["blackout", "unknown", "caution", "clear"] = Field(
        description="blackout: inside a high-impact event window; caution: medium-impact window or high-impact "
                    "event soon; unknown: calendar missing/stale (never reported as clear)")
    reasons: list[str]
    active_events: list[NewsEventOut]
    next_event: NewsEventOut | None
    countdown_s: int | None = Field(description="Seconds until the next relevant high/medium-impact event")
    blackout_until: datetime | None
    currencies: list[str] = Field(description="Calendar currencies that affect this instrument")
    calendar_updated_at: datetime | None
    rules: str = ("High impact: blackout 30 min before to 30 min after; caution if within 2 h. Medium impact: "
                  "caution 15 min before to 15 min after. Crypto: high-impact USD events only.")
    source: str = CALENDAR_SOURCE
    disclaimer: str = DISCLAIMER


class NewsItemOut(BaseModel):
    id: int
    source: str = Field(description="Feed code, e.g. fed, ecb, coindesk")
    source_name: str
    kind: Literal["central_bank", "regulator", "headline"]
    title: str
    url: str = Field(description="The publisher's page; the app links out (no article text is stored)")
    published_at: datetime
    age_s: int
    impact: Literal["high", "medium", "low"] = Field(description="Keyword rule on the headline (see `method`)")
    impact_reason: str
    assets: list[str] = Field(description="Currencies, metals, energy and coins the headline names (USD, XAU, BTC...)")


class NewsSourceOut(BaseModel):
    code: str
    name: str
    kind: Literal["central_bank", "regulator", "headline"]
    ok: bool = Field(description="Last fetch succeeded")
    last_ok_at: datetime | None
    last_error: str | None


class NewsFeedOut(BaseModel):
    items: list[NewsItemOut] = Field(description="Newest first")
    next_before_id: int | None
    sources: list[NewsSourceOut]
    updated_at: datetime | None = Field(description="Most recent successful fetch of any feed")
    method: str
    coverage: str = ("Official central-bank and regulator feeds, and publisher headline feeds (title and link only). "
                     "Social media posts are not included: they need a paid API.")
    disclaimer: str = DISCLAIMER

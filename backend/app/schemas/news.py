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

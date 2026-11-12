"""Watchlists, devices (FCM tokens), alerts and the alert inbox."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator

from ml.calibration.strength import TIER_LEVELS

EarnedTier = Literal["Strong", "Good", "Moderate", "Weak"]
assert set(EarnedTier.__args__) == {t for t, _ in TIER_LEVELS}  # type: ignore[attr-defined]
SymbolField = Annotated[str, Field(min_length=3, max_length=40)]


# ---- watchlists -------------------------------------------------------------------------------------------------

class WatchlistIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    symbols: list[SymbolField] = Field(default_factory=list, max_length=100)


class WatchlistUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    sort_order: int | None = Field(default=None, ge=0, le=10_000)


class WatchlistItemsIn(BaseModel):
    symbols: list[SymbolField] = Field(max_length=100, description="Full ordered list (replaces the items)")


class WatchlistItemIn(BaseModel):
    symbol: SymbolField


class WatchlistItemOut(BaseModel):
    symbol: str
    display_name: str
    asset_class: str
    sort_order: int


class WatchlistOut(BaseModel):
    id: int
    name: str
    sort_order: int
    created_at: datetime
    items: list[WatchlistItemOut]


class QuoteSignalOut(BaseModel):
    id: int
    timeframe: str
    horizon: int
    direction: Literal["up", "down"]
    strength: str
    confidence: float
    created_at: datetime
    has_demonstrated_edge: bool


class QuoteOut(BaseModel):
    symbol: str
    display_name: str
    price: float | None = Field(description="Close of the latest stored closed candle")
    as_of: datetime | None
    change_24h_pct: float | None
    news_state: str
    next_event: str | None
    next_event_in_s: int | None
    latest_signal: QuoteSignalOut | None


class QuotesOut(BaseModel):
    watchlist_id: int
    items: list[QuoteOut]
    note: str = "Prices are the last closed candle, not live ticks. Not financial advice."


# ---- devices ----------------------------------------------------------------------------------------------------

class DeviceIn(BaseModel):
    fcm_token: str = Field(min_length=20, max_length=4096)
    platform: Literal["android", "ios", "web"]
    app_version: str | None = Field(default=None, max_length=32)


class DeviceOut(BaseModel):
    id: int
    platform: str
    app_version: str | None
    token_hint: str = Field(description="Last 6 characters of the FCM token")
    created_at: datetime
    last_seen_at: datetime


# ---- alerts -----------------------------------------------------------------------------------------------------

class PriceCrossParams(BaseModel):
    level: float = Field(gt=0)
    direction: Literal["above", "below"] = Field(description="Fires when a closed candle crosses the level "
                                                             "(wick counts) from the other side")


class PctMoveParams(BaseModel):
    pct: float = Field(gt=0, le=50, description="Move in % between closes")
    window_candles: int = Field(default=4, ge=1, le=96)
    direction: Literal["up", "down", "either"] = "either"


class SignalParams(BaseModel):
    min_strength: EarnedTier = Field(description="Earned strength tier; 'Very Weak - Wait' signals never alert")
    horizons: list[int] | None = Field(default=None, max_length=5)


class NewsParams(BaseModel):
    lead_minutes: int = Field(default=30, ge=5, le=240)
    min_impact: Literal["high", "medium"] = "high"


PARAMS: dict[str, type[BaseModel]] = {"price_cross": PriceCrossParams, "pct_move": PctMoveParams,
                                      "signal": SignalParams, "news": NewsParams}
AlertKind = Literal["price_cross", "pct_move", "signal", "news"]


class AlertIn(BaseModel):
    kind: AlertKind
    symbol: SymbolField | None = Field(default=None, description="Required for price_cross and pct_move")
    watchlist_id: int | None = Field(default=None, ge=1, description="signal/news: every instrument in a list")
    timeframe: str | None = Field(default=None, max_length=8,
                                  description="price/pct: candles to evaluate (default 15m); signal: filter")
    params: dict[str, Any]
    recurring: bool | None = Field(default=None, description="Default: false for price/pct, true for signal/news")
    cooldown_s: int | None = Field(default=None, ge=0, le=7 * 86400)
    note: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def _validate(self) -> AlertIn:
        self.params = PARAMS[self.kind].model_validate(self.params).model_dump()
        if self.kind in ("price_cross", "pct_move"):
            if not self.symbol or self.watchlist_id is not None:
                raise ValueError(f"{self.kind} alerts need a symbol (and no watchlist_id)")
            self.timeframe = self.timeframe or "15m"
        elif self.symbol and self.watchlist_id is not None:
            raise ValueError("give a symbol or a watchlist_id, not both")
        return self


class AlertUpdate(BaseModel):
    params: dict[str, Any] | None = None
    active: bool | None = None
    recurring: bool | None = None
    cooldown_s: int | None = Field(default=None, ge=0, le=7 * 86400)
    note: str | None = Field(default=None, max_length=120)


class AlertOut(BaseModel):
    id: int
    kind: AlertKind
    symbol: str | None
    watchlist_id: int | None
    timeframe: str | None
    params: dict[str, Any]
    active: bool
    recurring: bool
    cooldown_s: int
    note: str | None
    last_triggered_at: datetime | None
    trigger_count: int
    created_at: datetime


class AlertEventOut(BaseModel):
    id: int
    alert_id: int | None
    kind: str
    title: str
    body: str
    data: dict[str, Any]
    triggered_at: datetime
    delivery: Literal["pending", "sent", "partial", "failed", "no_devices", "disabled"]
    read_at: datetime | None


class AlertEventPage(BaseModel):
    items: list[AlertEventOut]
    unread: int
    next_before_id: int | None


class MarkReadIn(BaseModel):
    ids: list[int] | None = Field(default=None, max_length=500)
    all: bool = False

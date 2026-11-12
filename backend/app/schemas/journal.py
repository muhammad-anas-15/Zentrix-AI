"""Journal, risk profile and risk status schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.signals import DISCLAIMER

Side = Literal["long", "short"]
Currency = Literal["USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "NZD", "USDT"]


def _tags(v: list[str] | None) -> list[str] | None:
    if v is None:
        return v
    out = sorted({t.strip().lower() for t in v if t.strip()})
    if len(out) > 10 or any(len(t) > 32 for t in out):
        raise ValueError("up to 10 tags of at most 32 characters")
    return out


class JournalBase(BaseModel):
    exit_price: float | None = Field(default=None, gt=0)
    exit_at: datetime | None = None
    stop_loss: float | None = Field(default=None, gt=0)
    take_profit: float | None = Field(default=None, gt=0)
    fees: float | None = Field(default=None, ge=0, description="Total costs in account currency")
    fx_rate: float | None = Field(default=None, gt=0,
                                  description="1 quote-currency unit in account currency; default: stored rate")
    timeframe: str | None = Field(default=None, max_length=8)
    signal_id: int | None = Field(default=None, ge=1, description="Signal that motivated the trade, if any")
    setup: str | None = Field(default=None, max_length=64)
    tags: list[str] | None = None
    notes: str | None = Field(default=None, max_length=4000)

    _norm_tags = field_validator("tags")(_tags)


class JournalIn(JournalBase):
    symbol: str = Field(min_length=3, max_length=40)
    side: Side
    quantity: float = Field(gt=0, description="Units of the base asset (1 standard FX lot = 100000)")
    entry_price: float = Field(gt=0)
    entry_at: datetime
    account_currency: Currency | None = Field(default=None, description="Default: risk profile or USD")

    @model_validator(mode="after")
    def _exit_pair(self) -> JournalIn:
        if (self.exit_price is None) != (self.exit_at is None):
            raise ValueError("exit_price and exit_at go together")
        return self


class JournalUpdate(JournalBase):
    """Partial update; send exit_price + exit_at to close an open trade, or null both to reopen."""

    side: Side | None = None
    quantity: float | None = Field(default=None, gt=0)
    entry_price: float | None = Field(default=None, gt=0)
    entry_at: datetime | None = None


class JournalOut(BaseModel):
    id: int
    symbol: str
    side: Side
    status: Literal["open", "closed"]
    quantity: float
    entry_price: float
    entry_at: datetime
    exit_price: float | None
    exit_at: datetime | None
    stop_loss: float | None
    take_profit: float | None
    fees: float
    account_currency: str
    fx_rate: float | None
    risk_account: float | None = Field(description="Money at risk at the stop, account currency")
    pnl_quote: float | None
    pnl_account: float | None = Field(description="After fees")
    r_multiple: float | None
    timeframe: str | None
    signal_id: int | None
    setup: str | None
    tags: list[str]
    notes: str | None
    created_at: datetime
    updated_at: datetime
    calc_notes: list[str] = []


class JournalPage(BaseModel):
    items: list[JournalOut]
    next_before_id: int | None


class JournalStatsOut(BaseModel):
    account_currency: str
    trades: int
    open: int
    closed: int
    counted: int = Field(description="Closed trades in this account currency with a computed P&L")
    excluded: int
    wins: int
    losses: int
    breakeven: int
    win_rate: float | None
    net_pnl: float
    avg_win: float | None
    avg_loss: float | None
    profit_factor: float | None
    expectancy: float | None = Field(description="Average P&L per counted trade")
    avg_r: float | None
    max_consecutive_losses: int
    by_instrument: list[dict[str, Any]]
    disclaimer: str = "Statistics of your own journal. Past results do not predict future results."


class InsightOut(BaseModel):
    code: str
    severity: Literal["info", "warning"]
    message: str
    evidence: dict[str, Any]


class JournalReviewOut(BaseModel):
    trades_reviewed: int
    insights: list[InsightOut]
    note: str
    method: str = ("Rules over your closed trades: holding time of losers vs winners, missing stops, risk "
                   "consistency, winner size in R, trades opened in high-impact news windows, days above your trade "
                   "limit, re-entries within 15 minutes of a loss.")


class RiskProfileIn(BaseModel):
    account_currency: Currency = "USD"
    balance: float | None = Field(default=None, gt=0)
    risk_per_trade_pct: float = Field(default=1.0, gt=0, le=100)
    max_daily_loss_pct: float = Field(default=3.0, gt=0, le=100)
    max_trades_per_day: int = Field(default=6, ge=1, le=200)
    max_consecutive_losses: int = Field(default=3, ge=1, le=50)
    leverage: float | None = Field(default=None, ge=1, le=3000)


class RiskProfileOut(RiskProfileIn):
    is_default: bool = Field(description="True until the user saves a profile")


class RiskWarningOut(BaseModel):
    code: str
    message: str


class RiskStatusOut(BaseModel):
    level: Literal["ok", "warning", "stop"]
    warnings: list[RiskWarningOut]
    day_start: datetime
    timezone: str
    account_currency: str
    realized_pnl_today: float
    daily_loss_limit: float | None = Field(description="balance x max_daily_loss_pct; null without a balance")
    daily_loss_used: float
    daily_loss_left: float | None
    trades_today: int
    max_trades_per_day: int
    open_positions: int
    open_risk: float = Field(description="Sum of money at risk on open journal trades with a stop")
    consecutive_losses: int
    profile_is_default: bool
    excluded_other_currency: int
    disclaimer: str = DISCLAIMER

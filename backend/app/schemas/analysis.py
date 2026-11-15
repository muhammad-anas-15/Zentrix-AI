"""Schemas for the analysis and risk tools (conditions, levels, position size, exit advice, scenario)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.news import NewsEventOut
from app.schemas.plans import PremiumBadge, locked_field, premium_field
from app.schemas.signals import DISCLAIMER

Side = Literal["long", "short"]


class FactorOut(BaseModel):
    name: str
    status: Literal["ok", "info", "caution", "danger", "unknown"]
    value: Any
    detail: str


class ConditionsOut(BaseModel):
    symbol: str
    venue: str
    timeframe: str
    light: Literal["green", "amber", "red", "unknown"]
    factors: list[FactorOut]
    trend: dict[str, Any]
    volatility: dict[str, Any]
    sessions: list[str] = Field(description="FX centres open now (local business hours)")
    last_candle_close: datetime | None
    method: str
    disclaimer: str = DISCLAIMER


class BaseRateOut(BaseModel):
    r: float
    entries: int
    target_first: int
    stop_first: int
    neither_within_max_bars: int
    max_bars: int
    hit_rate: float | None = Field(description="target_first / (target_first + stop_first) on past candles")
    ci95: list[float | None] | None
    break_even_hit_rate: float = Field(description="1 / (1 + R): hit rate needed to break even before costs")


class TargetOut(BaseModel):
    r: float
    price: float | None
    base_rate: BaseRateOut


class LevelsOut(BaseModel):
    symbol: str
    venue: str
    timeframe: str
    side: Side
    entry: float | None
    atr: float | None
    atr_period: int = 14
    sl_atr: float
    stop: float | None
    targets: list[TargetOut]
    support: float | None
    resistance: float | None
    as_of: datetime = Field(description="Close time of the candle the levels are computed from")
    signal_id: int | None = None
    notes: list[str] = []
    method: str
    premium: PremiumBadge = premium_field("trade_levels")
    disclaimer: str = DISCLAIMER


class PositionSizeIn(BaseModel):
    symbol: str = Field(min_length=3, max_length=40)
    entry: float = Field(gt=0)
    stop: float = Field(gt=0, description="Stop-loss price; it decides the side (below entry = long)")
    take_profit: float | None = Field(default=None, gt=0)
    account_currency: str | None = Field(default=None, max_length=8, description="Default: risk profile or USD")
    balance: float | None = Field(default=None, gt=0, description="Default: risk profile")
    risk_pct: float | None = Field(default=None, gt=0, le=100, description="Default: risk profile or 1%")
    risk_amount: float | None = Field(default=None, gt=0, description="Overrides balance x risk_pct")
    conversion_rate: float | None = Field(default=None, gt=0,
                                          description="1 unit of the quote currency in account currency")
    leverage: float | None = Field(default=None, ge=1, le=3000)
    lot_step: float = Field(default=0.01, gt=0)
    size_step: float | None = Field(default=None, gt=0, description="Unit step for non-lot assets (crypto)")
    timeframe: str | None = Field(default="15m", max_length=8, description="ATR timeframe for the stop check")


class PositionSizeOut(BaseModel):
    symbol: str
    side: Side
    account_currency: str
    units: float
    lots: float | None = Field(description="Lots of instruments.contract_size (null for crypto)")
    contract_size: float | None
    risk_amount: float = Field(description="Money lost if the stop is hit (account currency, before costs)")
    risk_pct: float | None
    stop_distance: float
    stop_pips: float | None
    stop_atr: float | None
    pip_size: float | None
    pip_value_per_lot: float | None
    point_size: float
    reward_amount: float | None
    risk_reward: float | None
    notional: float
    margin: float | None
    conversion_rate: float
    conversion_notes: list[str]
    daily_loss_left: float | None = Field(description="Signed-in users: remaining daily loss budget (Premium: "
                                                      "risk_guard)")
    warnings: list[str]
    premium_locked: list[str] = locked_field()
    disclaimer: str = DISCLAIMER


class ExitAdviceIn(BaseModel):
    symbol: str = Field(min_length=3, max_length=40)
    timeframe: str = Field(default="15m", max_length=8)
    venue: str | None = Field(default=None, max_length=32)
    side: Side
    entry_price: float = Field(gt=0)
    stop_loss: float | None = Field(default=None, gt=0)
    take_profit: float | None = Field(default=None, gt=0)
    opened_at: datetime | None = None

    @model_validator(mode="after")
    def _sides(self) -> ExitAdviceIn:
        s = 1 if self.side == "long" else -1
        if self.stop_loss is not None and (self.entry_price - self.stop_loss) * s <= 0:
            raise ValueError(f"stop_loss must be {'below' if s == 1 else 'above'} entry for a {self.side}")
        if self.take_profit is not None and (self.take_profit - self.entry_price) * s <= 0:
            raise ValueError(f"take_profit must be {'above' if s == 1 else 'below'} entry for a {self.side}")
        return self


class ExitAdviceOut(BaseModel):
    symbol: str
    timeframe: str
    side: Side
    action: Literal["consider_exit", "take_partial", "tighten_stop", "hold"]
    reasons: list[str]
    notes: list[str]
    price: float
    as_of: datetime
    atr: float | None
    r_multiple: float | None = Field(description="Open profit in units of the initial stop distance")
    best_price: float
    suggested_stop: float | None
    trailing_stop: float | None
    stop_distance_atr: float | None
    target_distance_atr: float | None
    news_state: str
    method: str
    premium: PremiumBadge = premium_field("exit_advisor")
    premium_locked: list[str] = locked_field()
    disclaimer: str = DISCLAIMER


class ScenarioStepOut(BaseModel):
    k: int = Field(description="Candles ahead")
    at: datetime = Field(description="Approximate close time of that candle (market closures not skipped)")
    low: float | None
    median: float | None
    high: float | None
    nominal_coverage: float
    coverage: float | None = Field(description="Measured out-of-sample share of cases inside the band")
    coverage_ci95: list[float] | None
    coverage_tested: int
    history: int


class ScenarioDirectionOut(BaseModel):
    horizon: int
    model_key: str
    has_demonstrated_edge: bool
    reliable: bool = Field(description="False: no demonstrated edge; treat the direction as 50/50")
    p_up: float | None = Field(description="Calibrated P(up) of the latest signal on the latest candle")
    strength: str | None
    signal_id: int | None
    live_track_record: dict[str, Any]
    backtest_accuracy: float | None


class ScenarioOut(BaseModel):
    symbol: str
    venue: str
    timeframe: str
    last_close: float
    as_of: datetime
    steps: list[ScenarioStepOut]
    direction: list[ScenarioDirectionOut]
    premium: PremiumBadge = premium_field("scenario")
    premium_locked: list[str] = locked_field()
    method: str
    disclaimer: str = DISCLAIMER


class RadarItemOut(BaseModel):
    rank: int = 0
    symbol: str
    display_name: str
    asset_class: str
    venue: str | None
    price_decimals: int
    light: Literal["green", "amber", "red", "unknown"]
    reasons: list[str] = Field(default_factory=list, description="Why the light is not green (caution/danger inputs)")
    trend_regime: str | None = Field(default=None, description="trending / weak trend / ranging / unknown (ADX 14)")
    trend_direction: str | None = Field(default=None, description="up / down while trending (+DI vs -DI); null "
                                                                  "when ranging. Describes the past, not a forecast")
    adx: float | None = None
    volatility_regime: str | None = Field(default=None, description="low / normal / high / extreme")
    volatility_percentile: float | None = Field(default=None, description="ATR% vs the last 500 candles (0-100)")
    news_state: str
    next_event: NewsEventOut | None = None
    next_event_in_s: int | None = None
    sessions: list[str] = Field(default_factory=list)
    last_price: float | None = None
    last_candle_close: datetime | None = None
    change_24h_pct: float | None = None
    spark: list[float] = Field(default_factory=list, description="Closes over the last 24h (up to 96 points)")
    spark_from: datetime | None = None


class RadarOut(BaseModel):
    timeframe: str
    as_of: datetime
    items: list[RadarItemOut]
    ranking: str
    method: str
    disclaimer: str = DISCLAIMER

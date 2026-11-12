from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

DISCLAIMER = ("Not financial advice. Signals are probabilities from past data; the live track record below "
              "is the only measure of how they perform.")


class CandleOut(BaseModel):
    t: datetime = Field(description="Candle open time (UTC)")
    o: float
    h: float
    l: float  # noqa: E741
    c: float
    v: float | None


class CandlesOut(BaseModel):
    symbol: str
    venue: str
    timeframe: str
    candles: list[CandleOut] = Field(description="Closed, market-hours candles, oldest first")


class SignalOutcomeOut(BaseModel):
    outcome: Literal["win", "loss", "flat", "void"]
    entry_time: datetime | None
    entry_price: float | None
    exit_time: datetime | None
    exit_price: float | None
    move_pct: float | None
    resolved_at: datetime
    note: str | None


class SignalModelOut(BaseModel):
    key: str
    trained_at: datetime
    has_demonstrated_edge: bool = Field(description="False: the model showed no out-of-sample edge; every signal "
                                                    "is 'Very Weak - Wait'")


class SignalOut(BaseModel):
    id: int
    symbol: str
    venue: str
    timeframe: str
    horizon: int = Field(description="Candles ahead the signal refers to")
    candle_time: datetime = Field(description="Open time of the closed candle the signal was computed on")
    decision_at: datetime
    created_at: datetime
    direction: Literal["up", "down"]
    confidence: float = Field(description="Calibrated probability of the stated direction")
    p_up: float
    strength: str
    model: SignalModelOut
    backtest_tier: dict[str, Any] | None = Field(description="Out-of-sample BACKTEST stats of this strength tier "
                                                             "for this model (not live results)")
    outcome: SignalOutcomeOut | None


class SignalPage(BaseModel):
    items: list[SignalOut]
    next_before_id: int | None
    disclaimer: str = DISCLAIMER


class CountsOut(BaseModel):
    signals: int
    pending: int
    wins: int
    losses: int
    flats: int
    voids: int
    decided: int = Field(description="wins + losses")
    hit_rate: float | None = Field(description="wins / (wins + losses); null until any signal is decided")
    ci95: list[float | None] | None = Field(description="95% Wilson interval of the hit rate")


class StrengthCountsOut(CountsOut):
    strength: str


class TrackRecordOut(BaseModel):
    overall: CountsOut
    by_strength: list[StrengthCountsOut]
    first_signal_at: datetime | None
    last_signal_at: datetime | None
    filters: dict[str, Any]
    method: str = ("Live signals only (created within one timeframe of the candle close). Outcome: entry at the "
                   "next candle's open, exit at the open after the horizon. Flat and void outcomes are excluded "
                   "from the hit rate and listed separately.")
    disclaimer: str = DISCLAIMER


class BacktestOut(BaseModel):
    oos_signals: int | None
    accuracy: float | None
    ci95: list[float] | None
    majority_baseline: float | None
    period: dict[str, Any] | None


class ModelOut(BaseModel):
    key: str
    symbol: str
    venue: str
    timeframe: str
    horizon: int
    active: bool
    has_demonstrated_edge: bool
    reasons: list[str]
    label_mode: str
    trained_at: datetime
    backtest: BacktestOut
    note: str | None

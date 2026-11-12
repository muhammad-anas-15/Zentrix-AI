"""Position size and risk calculator (pure). Sizes are rounded DOWN so the money at risk never exceeds the
requested risk. Lot-based assets (FX, metals, commodity CFDs) use ``instruments.contract_size``; crypto uses
units of the base asset.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Spec:
    symbol: str
    asset_class: str
    base: str
    quote: str
    contract_size: float | None
    price_decimals: int


@dataclass
class SizeInput:
    entry: float
    stop: float
    take_profit: float | None
    balance: float | None
    risk_pct: float | None
    risk_amount: float | None
    quote_to_account: float
    lot_step: float = 0.01
    size_step: float | None = None
    leverage: float | None = None
    atr: float | None = None
    daily_loss_left: float | None = None  # remaining daily loss budget (account currency), if known


@dataclass
class SizeResult:
    side: str
    units: float
    lots: float | None
    risk_amount: float
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
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


class RiskInputError(ValueError):
    pass


def pip_size(spec: Spec) -> float | None:
    if spec.asset_class != "fx":
        return None
    return 0.01 if spec.quote == "JPY" else 0.0001


def floor_step(x: float, step: float) -> float:
    if step <= 0:
        return x
    n = math.floor(x / step + 1e-9)
    decimals = max(0, -math.floor(math.log10(step))) if step < 1 else 0
    return round(n * step, decimals + 2)


def position_size(spec: Spec, inp: SizeInput) -> SizeResult:
    if inp.entry <= 0 or inp.stop <= 0:
        raise RiskInputError("entry and stop must be positive prices")
    if inp.entry == inp.stop:
        raise RiskInputError("stop must differ from entry")
    side = "long" if inp.stop < inp.entry else "short"
    if inp.take_profit is not None and (inp.take_profit - inp.entry) * (1 if side == "long" else -1) <= 0:
        raise RiskInputError(f"take_profit must be {'above' if side == 'long' else 'below'} entry for a {side} "
                             "(the stop decides the side)")
    if inp.risk_amount is not None:
        budget = inp.risk_amount
    elif inp.balance is not None and inp.risk_pct is not None:
        budget = inp.balance * inp.risk_pct / 100
    else:
        raise RiskInputError("give risk_amount, or balance and risk_pct")
    if budget <= 0:
        raise RiskInputError("risk must be positive")

    dist = abs(inp.entry - inp.stop)
    loss_per_unit = dist * inp.quote_to_account
    raw_units = budget / loss_per_unit
    warnings: list[str] = []
    lots: float | None = None
    if spec.contract_size:
        lots = floor_step(raw_units / spec.contract_size, inp.lot_step)
        units = lots * spec.contract_size
        if lots == 0:
            min_risk = inp.lot_step * spec.contract_size * loss_per_unit
            warnings.append(f"risk is too small for the minimum size ({inp.lot_step} lot would risk "
                            f"{min_risk:.2f}); widen the risk or tighten the stop")
    else:
        units = floor_step(raw_units, inp.size_step) if inp.size_step else math.floor(raw_units * 1e8) / 1e8
        if units == 0:
            warnings.append("risk is too small for the minimum size step")

    risk_amount = units * loss_per_unit
    risk_pct = risk_amount / inp.balance * 100 if inp.balance else None
    ps = pip_size(spec)
    reward = abs(inp.take_profit - inp.entry) * units * inp.quote_to_account if inp.take_profit else None
    rr = abs(inp.take_profit - inp.entry) / dist if inp.take_profit else None
    notional = units * inp.entry * inp.quote_to_account
    margin = notional / inp.leverage if inp.leverage else None

    shown_pct = risk_pct if risk_pct is not None else inp.risk_pct
    if shown_pct is not None and shown_pct > 5:
        warnings.append(f"risking {shown_pct:.1f}% of the account on one trade: a short losing streak can wipe out "
                        "a large part of it (common guidance is 1-2%)")
    elif shown_pct is not None and shown_pct > 2:
        warnings.append(f"risking {shown_pct:.1f}% per trade is above the common 1-2% guideline")
    if rr is not None and rr < 1:
        warnings.append(f"reward:risk is {rr:.2f}: you need to win more than {1 / (1 + rr):.0%} of such trades to "
                        "break even before costs")
    stop_atr = dist / inp.atr if inp.atr else None
    if stop_atr is not None and stop_atr < 0.5:
        warnings.append(f"stop is {stop_atr:.2f} x ATR away: inside normal candle noise, likely to be hit by chance")
    if margin is not None and inp.balance is not None and margin > inp.balance:
        warnings.append(f"required margin {margin:.2f} exceeds the balance at {inp.leverage:g}:1 leverage")
    if inp.daily_loss_left is not None and risk_amount > inp.daily_loss_left:
        warnings.append(f"this trade risks {risk_amount:.2f} but only {max(inp.daily_loss_left, 0):.2f} is left "
                        "in today's loss limit")
    return SizeResult(
        side=side, units=units, lots=lots, risk_amount=risk_amount, risk_pct=risk_pct, stop_distance=dist,
        stop_pips=dist / ps if ps else None, stop_atr=stop_atr, pip_size=ps,
        pip_value_per_lot=ps * spec.contract_size * inp.quote_to_account if ps and spec.contract_size else None,
        point_size=10 ** -spec.price_decimals, reward_amount=reward, risk_reward=rr, notional=notional,
        margin=margin, warnings=warnings)

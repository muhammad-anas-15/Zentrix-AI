"""Trader-protection tools: market conditions, ATR levels, position size, exit advice, scenario path, pattern
projection.

Public with the IP rate limit; the position-size calculator personalises (risk profile, daily loss budget) when
a valid access token is sent. Levels, exit advice, the scenario path and the pattern projection are Premium
(``app/api/premium.py``).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import select

from app.api.deps import DbDep, NowDep, OptionalUser, SettingsDep
from app.api.premium import GateDep, partly_premium, premium
from app.core.errors import AppError
from app.core.ratelimit import limit_by_ip
from app.models.signals import ModelVersion, Signal
from app.schemas.analysis import (
    BaseRateOut,
    ConditionsOut,
    ExitAdviceIn,
    ExitAdviceOut,
    FactorOut,
    LevelsOut,
    PatternOutlookOut,
    PositionSizeIn,
    PositionSizeOut,
    ScenarioDirectionOut,
    ScenarioOut,
    ScenarioStepOut,
    TargetOut,
)
from app.services.analysis import conditions as cond
from app.services.analysis import exit_advisor, levels, patterns, scenario
from app.services.analysis.market import Series, load_market, rnd, support_resistance, with_atr
from app.services.marketdata.candles import load_series, ts_to_dt
from app.services.marketdata.lookup import instrument_by_symbol, listing_for
from app.services.news.guard import GuardConfig, GuardResult, guard_for
from app.services.risk.calculator import RiskInputError, SizeInput, Spec, position_size
from app.services.risk.conversion import ConversionUnavailable, quote_to_account
from app.services.risk.status import profile_values, risk_status
from app.services.signals.serialize import signal_to_dict
from app.services.signals.track_record import Filters, compute_track_record
from ml.data.candles import interval_seconds

router = APIRouter(dependencies=[Depends(limit_by_ip("public", "rate_limit_public"))])
SymbolQ = Annotated[str, Query(min_length=3, max_length=40, description="Canonical symbol, e.g. EUR/USD")]
TimeframeQ = Annotated[str, Query(max_length=8)]
VenueQ = Annotated[str | None, Query(max_length=32)]
RR_DEFAULT = (1.0, 2.0)


async def _guard(db: DbDep, s: Series, now: datetime, settings: SettingsDep) -> GuardResult:
    i = s.ref.instrument
    return await guard_for(db, i.asset_class, i.base, i.quote, now, GuardConfig.from_settings(settings))


def _as_of(s: Series) -> datetime:
    return ts_to_dt(int(s.candles["time"].iloc[-1]) + interval_seconds(s.timeframe))


@router.get("/conditions", response_model=ConditionsOut, tags=["tools"],
            summary="Market-condition light: trend/range, volatility, session, news, data freshness")
async def get_conditions(db: DbDep, now: NowDep, settings: SettingsDep, symbol: SymbolQ,
                         timeframe: TimeframeQ = "15m", venue: VenueQ = None) -> ConditionsOut:
    s = await load_market(db, symbol, timeframe, venue, n=600, min_candles=60)
    c = cond.assess(s.candles, timeframe, s.ref.instrument.session, now, await _guard(db, s, now, settings))
    return ConditionsOut(symbol=symbol, venue=s.ref.venue, timeframe=timeframe, light=c.light,  # type: ignore[arg-type]
                         factors=[FactorOut(**f.as_dict()) for f in c.factors], trend=c.trend,
                         volatility=c.volatility, sessions=c.sessions, last_candle_close=c.last_candle_close,
                         method=cond.METHOD)


def _levels_out(s: Series, side: str, entry: float | None, sl_atr: float, rr: tuple[float, ...],
                max_bars: int, signal_id: int | None = None, notes: list[str] | None = None) -> LevelsOut:
    a = with_atr(s.candles).iloc[-1]
    entry = entry if entry is not None else float(s.candles["close"].iloc[-1])
    sup, res = support_resistance(s.candles)
    d = s.decimals
    notes = list(notes or [])
    if not a == a:  # NaN: fewer candles than the ATR period
        raise AppError(404, "no_data", "Not enough candles for ATR")
    lv = levels.compute_levels(entry, float(a), side, sl_atr, rr)
    if (side == "long" and lv.stop < sup) or (side == "short" and lv.stop > res):
        notes.append(f"stop lies beyond the recent {'support' if side == 'long' else 'resistance'} "
                     f"({rnd(sup if side == 'long' else res, d)})")
    targets = [TargetOut(r=r, price=rnd(p, d), base_rate=BaseRateOut(
        **levels.base_rate(s.candles, side, sl_atr, r, max_bars=max_bars))) for r, p in lv.targets]
    return LevelsOut(symbol=s.symbol, venue=s.ref.venue, timeframe=s.timeframe, side=side,  # type: ignore[arg-type]
                     entry=rnd(entry, d), atr=rnd(lv.atr, d + 2), sl_atr=sl_atr, stop=rnd(lv.stop, d),
                     targets=targets, support=rnd(sup, d), resistance=rnd(res, d), as_of=_as_of(s),
                     signal_id=signal_id, notes=notes, method=levels.METHOD)


@router.get("/levels", response_model=LevelsOut, tags=["tools"],
            summary="ATR stop-loss / take-profit levels with their historical base rate (Premium)",
            **premium("trade_levels"))
async def get_levels(
    db: DbDep, symbol: SymbolQ, side: Annotated[str, Query(pattern="^(long|short)$")],
    timeframe: TimeframeQ = "15m", venue: VenueQ = None,
    entry: Annotated[float | None, Query(gt=0, description="Default: latest close")] = None,
    sl_atr: Annotated[float, Query(gt=0, le=10)] = 1.5,
    rr: Annotated[list[float] | None, Query(description="Target R multiples (default 1 and 2)")] = None,
    max_bars: Annotated[int, Query(ge=5, le=200)] = 50,
) -> LevelsOut:
    targets = tuple(rr) if rr else RR_DEFAULT
    if len(targets) > 4 or any(not 0 < r <= 10 for r in targets):
        raise AppError(422, "validation_error", "rr: up to 4 values in (0, 10]")
    s = await load_market(db, symbol, timeframe, venue, n=1100, min_candles=60)
    return _levels_out(s, side, entry, sl_atr, targets, max_bars)


@router.get("/signals/{signal_id}/levels", response_model=LevelsOut, tags=["signals"],
            summary="ATR levels for a signal, computed from the candles known when it was made (Premium)",
            **premium("trade_levels"))
async def signal_levels(db: DbDep, gate: GateDep, signal_id: Annotated[int, Path(ge=1)],
                        sl_atr: Annotated[float, Query(gt=0, le=10)] = 1.5,
                        max_bars: Annotated[int, Query(ge=5, le=200)] = 50) -> LevelsOut:
    sig = await db.get(Signal, signal_id)
    if sig is None:
        raise AppError(404, "not_found", f"No signal {signal_id}")
    if sig.outcome is None:  # the side would reveal a live signal of a premium market
        gate.require_market(sig.instrument.symbol, sig.timeframe)
    candles = await load_series(db, sig.listing_id, sig.timeframe, 1100, until=sig.candle_ts)
    if len(candles) < 60:
        raise AppError(404, "no_data", "Not enough stored candles before this signal")
    ref = await listing_for(db, sig.instrument.symbol, sig.listing.venue.code)
    side = "long" if sig.direction == "up" else "short"
    notes = ["entry = close of the signal candle; a real entry fills at the next candle's open"]
    if not sig.model_usable:
        notes.append("this signal's model has no demonstrated edge: the levels describe risk, not an opportunity")
    return _levels_out(Series(ref, sig.timeframe, candles), side, None, sl_atr, RR_DEFAULT, max_bars, sig.id, notes)


@router.post("/risk/position-size", response_model=PositionSizeOut, tags=["risk"],
             summary="Position size, money at risk, pip value, R:R and margin, with warnings",
             **partly_premium("risk_guard"))
async def post_position_size(body: PositionSizeIn, db: DbDep, now: NowDep, user: OptionalUser,
                             gate: GateDep) -> PositionSizeOut:
    inst = await instrument_by_symbol(db, body.symbol)
    pv = await profile_values(db, user) if user else None
    account = (body.account_currency or (pv.account_currency if pv else "USD")).upper()
    balance = body.balance if body.balance is not None else (pv.balance if pv else None)
    risk_pct = body.risk_pct if body.risk_pct is not None else (pv.risk_per_trade_pct if pv else 1.0)
    leverage = body.leverage if body.leverage is not None else (pv.leverage if pv else None)
    if body.conversion_rate is not None:
        rate, rate_notes = body.conversion_rate, ["conversion rate supplied by the client"]
    else:
        try:
            r = await quote_to_account(db, inst.quote, account)
        except ConversionUnavailable as exc:
            raise AppError(422, "conversion_unavailable", str(exc)) from exc
        rate, rate_notes = r.rate, r.notes
    atr_value = None
    if body.timeframe:
        try:
            s = await load_market(db, body.symbol, body.timeframe, n=100, min_candles=20)
            a = with_atr(s.candles).iloc[-1]
            atr_value = float(a) if a == a else None
        except AppError:
            atr_value = None
    left, locked = None, []
    if user is not None and pv is not None and account == pv.account_currency:
        if gate.allows("risk_guard"):
            left = (await risk_status(db, user, now))["daily_loss_left"]
        else:
            locked = ["risk_guard"]
    spec = Spec(inst.symbol, inst.asset_class, inst.base, inst.quote, inst.contract_size, inst.price_decimals)
    try:
        res = position_size(spec, SizeInput(body.entry, body.stop, body.take_profit, balance, risk_pct,
                                            body.risk_amount, rate, body.lot_step, body.size_step, leverage,
                                            atr_value, left))
    except RiskInputError as exc:
        raise AppError(422, "invalid_risk_input", str(exc)) from exc
    return PositionSizeOut(symbol=inst.symbol, account_currency=account, contract_size=inst.contract_size,
                           conversion_rate=rate, conversion_notes=rate_notes, daily_loss_left=left,
                           premium_locked=locked, **res.as_dict())


async def _latest_signal(db: DbDep, listing_id: int, timeframe: str, candle_ts: datetime,
                         horizon: int | None = 1) -> Signal | None:
    stmt = select(Signal).where(Signal.listing_id == listing_id, Signal.timeframe == timeframe,
                                Signal.candle_ts == candle_ts)
    if horizon is not None:
        stmt = stmt.where(Signal.horizon == horizon)
    return (await db.scalars(stmt.order_by(Signal.id.desc()).limit(1))).unique().first()


@router.post("/exit-advice", response_model=ExitAdviceOut, tags=["tools"],
             summary="Exit advisor for an open position (hold / tighten stop / take partial / consider exit) "
                     "(Premium)", **premium("exit_advisor"))
async def post_exit_advice(body: ExitAdviceIn, db: DbDep, now: NowDep, settings: SettingsDep,
                           gate: GateDep) -> ExitAdviceOut:
    s = await load_market(db, body.symbol, body.timeframe, body.venue, n=300, min_candles=30)
    guard = await _guard(db, s, now, settings)
    last_open = ts_to_dt(int(s.candles["time"].iloc[-1]))
    market_open = gate.market_open(body.symbol, body.timeframe)  # else: no live signal of a premium market
    sig = await _latest_signal(db, s.ref.listing.id, body.timeframe, last_open) if market_open else None
    opened = int(body.opened_at.timestamp()) // interval_seconds(body.timeframe) * interval_seconds(body.timeframe) \
        if body.opened_at else None
    out = exit_advisor.advise(s.candles, body.side, body.entry_price, body.stop_loss, body.take_profit, opened,
                              guard, signal_to_dict(sig) if sig else None)
    return ExitAdviceOut(symbol=body.symbol, timeframe=body.timeframe, side=body.side, as_of=_as_of(s),
                         news_state=guard.state, method=exit_advisor.METHOD,
                         premium_locked=[] if market_open else ["all_markets"], **out)


@router.get("/patterns", response_model=PatternOutlookOut, tags=["tools"],
            summary="Technical Pattern Projection: pattern now, structure, and what followed it over 1-5 candles "
                    "(Premium)",
            **premium("pattern_outlook"))
async def get_patterns(db: DbDep, symbol: SymbolQ, timeframe: TimeframeQ = "15m", venue: VenueQ = None,
                       steps: Annotated[int, Query(ge=3, le=5)] = 5) -> PatternOutlookOut:
    s = await load_market(db, symbol, timeframe, venue, n=5000, min_candles=120)
    out = patterns.outlook(s.candles, steps)
    as_of = _as_of(s)
    tf_s = interval_seconds(timeframe)
    d = s.decimals + 1  # one extra digit: projected values are not prices that traded
    projection = out["projection"]
    if projection is not None:
        projection["steps"] = [
            {**step, "at": as_of + timedelta(seconds=tf_s * step["k"]),
             **{k: rnd(step[k], d) for k in ("open", "high", "low", "close", "band_low", "band_high")}}
            for step in projection["steps"]]
    pattern = out["pattern"]
    if pattern is not None:
        pattern["starts"] = ts_to_dt(pattern["starts"])
    return PatternOutlookOut(symbol=symbol, venue=s.ref.venue, timeframe=timeframe, as_of=as_of,
                             last_close=out["last_close"], atr=rnd(out["atr"], d), label=patterns.LABEL,
                             pattern=pattern, structure=out["structure"], projection=projection,
                             base_rate=out["base_rate"], history=out["history"], method=patterns.METHOD)


@router.get("/scenario", response_model=ScenarioOut, tags=["tools"],
            summary="Scenario path for the next 1-5 candles with measured band coverage (Premium)",
            **premium("scenario"))
async def get_scenario(db: DbDep, gate: GateDep, symbol: SymbolQ, timeframe: TimeframeQ = "15m",
                       venue: VenueQ = None, steps: Annotated[int, Query(ge=1, le=5)] = 5) -> ScenarioOut:
    s = await load_market(db, symbol, timeframe, venue, n=1300, min_candles=300)
    tf_s = interval_seconds(timeframe)
    as_of = _as_of(s)
    step_rows = [ScenarioStepOut(at=as_of + timedelta(seconds=tf_s * b["k"]), **b)
                 for b in scenario.bands(s.candles, steps)]
    last_open = ts_to_dt(int(s.candles["time"].iloc[-1]))
    market_open = gate.market_open(symbol, timeframe)  # else: no live signal of a premium market
    directions = []
    versions = (await db.scalars(select(ModelVersion).where(
        ModelVersion.listing_id == s.ref.listing.id, ModelVersion.timeframe == timeframe, ModelVersion.active)
        .order_by(ModelVersion.horizon))).all()
    for mv in versions:
        sig = None if not market_open else (await db.scalars(select(Signal).where(
            Signal.model_version_id == mv.id, Signal.candle_ts == last_open))).unique().first()
        tr: dict[str, Any] = (await compute_track_record(db, Filters(model_version_id=mv.id)))["overall"]
        acc = (mv.metrics or {}).get("accuracy") or {}
        directions.append(ScenarioDirectionOut(
            horizon=mv.horizon, model_key=mv.key, has_demonstrated_edge=mv.usable,
            reliable=bool(mv.usable and sig is not None and sig.strength != "Very Weak - Wait"),
            p_up=sig.p_up if sig else None, strength=sig.strength if sig else None,
            signal_id=sig.id if sig else None, live_track_record=tr, backtest_accuracy=acc.get("rate")))
    return ScenarioOut(symbol=symbol, venue=s.ref.venue, timeframe=timeframe,
                       last_close=float(s.candles["close"].iloc[-1]), as_of=as_of, steps=step_rows,
                       direction=directions, method=scenario.METHOD,
                       premium_locked=[] if market_open else ["all_markets"])


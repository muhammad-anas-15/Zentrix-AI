"""Market Radar: every ingested market at a glance, ranked by conditions then activity. Free (market_conditions).

It describes the market now (condition light, trend, volatility regime, news state, recent movement). It makes no
direction call: the ranking puts tradeable conditions first, not a predicted winner.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api.deps import DbDep, NowDep, SettingsDep
from app.core.errors import AppError
from app.core.ratelimit import limit_by_ip
from app.models.market import Instrument, InstrumentListing, Timeframe
from app.models.signals import IngestionTarget
from app.schemas.analysis import RadarItemOut, RadarOut
from app.schemas.news import NewsEventOut
from app.services.analysis import conditions as cond
from app.services.analysis.market import load_market, rnd
from app.services.news.guard import GuardConfig, calendar_updated_at, evaluate_guard, instrument_currencies, load_events
from ml.data.candles import interval_seconds

router = APIRouter(tags=["tools"], dependencies=[Depends(limit_by_ip("public", "rate_limit_public"))])
MAX_MARKETS = 30
SPARK_POINTS = 96
LIGHT_ORDER = {"green": 0, "amber": 1, "red": 2, "unknown": 3}
RANKING = ("Condition light first (green, amber, red, unknown), then activity: the volatility percentile, most "
           "active first. Ranking describes conditions now, not a predicted direction.")


async def _default_symbols(db: DbDep, timeframe: str) -> list[str]:
    """Instruments whose primary listing is ingested at this timeframe."""
    rows = await db.scalars(
        select(Instrument.symbol).join(InstrumentListing, InstrumentListing.instrument_id == Instrument.id)
        .join(IngestionTarget, IngestionTarget.listing_id == InstrumentListing.id)
        .where(IngestionTarget.timeframe == timeframe, IngestionTarget.enabled, InstrumentListing.is_primary)
        .distinct().order_by(Instrument.symbol))
    return list(rows.all())[:MAX_MARKETS]


def _spark(closes: list[float]) -> list[float]:
    if len(closes) <= SPARK_POINTS:
        return closes
    step = len(closes) / SPARK_POINTS
    return [closes[int(i * step)] for i in range(SPARK_POINTS - 1)] + [closes[-1]]


@router.get("/radar", response_model=RadarOut,
            summary="Market Radar: every ingested market ranked by conditions, then activity (no direction calls)")
async def get_radar(
    db: DbDep, now: NowDep, settings: SettingsDep,
    timeframe: Annotated[str, Query(max_length=8)] = "15m",
    symbols: Annotated[str | None, Query(max_length=600, description="Comma-separated canonical symbols. "
                                         "Default: every market ingested at this timeframe")] = None,
) -> RadarOut:
    if await db.scalar(select(Timeframe.code).where(Timeframe.code == timeframe)) is None:
        raise AppError(422, "unknown_timeframe", f"Unknown timeframe {timeframe}")
    wanted = [s.strip() for s in symbols.split(",") if s.strip()][:MAX_MARKETS] if symbols \
        else await _default_symbols(db, timeframe)
    found = {i.symbol: i for i in (await db.scalars(select(Instrument).where(Instrument.symbol.in_(wanted)))).all()}
    missing = [s for s in wanted if s not in found]
    if missing:
        raise AppError(422, "unknown_instrument", f"Unknown symbols: {', '.join(missing)}", details=missing)

    cfg = GuardConfig.from_settings(settings)
    scopes = {s: instrument_currencies(found[s].asset_class, found[s].base, found[s].quote) for s in wanted}
    currencies = frozenset().union(*(c for c, _ in scopes.values())) if scopes else frozenset()
    events = await load_events(db, currencies, now - timedelta(seconds=cfg.blackout_after_s), now + timedelta(days=8))
    updated = await calendar_updated_at(db)
    tf_s = interval_seconds(timeframe)

    items: list[RadarItemOut] = []
    for sym in wanted:
        inst = found[sym]
        cur, high_only = scopes[sym]
        g = evaluate_guard(events, cur, high_only, now, cfg, updated)
        next_event = NewsEventOut(**g.next_event) if g.next_event else None
        base: dict[str, Any] = {"symbol": sym, "display_name": inst.display_name, "asset_class": inst.asset_class,
                "price_decimals": inst.price_decimals, "news_state": g.state, "next_event": next_event,
                "next_event_in_s": g.countdown_s}
        try:
            s = await load_market(db, sym, timeframe, None, n=600, min_candles=60)
        except AppError as exc:
            if exc.code != "no_data":
                raise
            items.append(RadarItemOut(**base, venue=None, light="unknown", reasons=["no stored candles yet"]))
            continue
        c = cond.assess(s.candles, timeframe, inst.session, now, g)
        times = s.candles["time"].to_numpy()
        closes = [float(x) for x in s.candles["close"].to_numpy()]
        last_t = int(times[-1])
        day = [closes[i] for i in range(len(closes)) if int(times[i]) > last_t - 86_400]
        prior = [closes[i] for i in range(len(closes)) if int(times[i]) <= last_t - 86_400]
        change = (closes[-1] / prior[-1] - 1) * 100 if prior and prior[-1] else None
        d = inst.price_decimals
        items.append(RadarItemOut(
            **base, venue=s.ref.venue, light=c.light,  # type: ignore[arg-type]
            reasons=[f.detail for f in c.factors if f.status in ("danger", "caution")],
            trend_regime=c.trend.get("regime"), trend_direction=c.trend.get("direction"), adx=c.trend.get("adx"),
            volatility_regime=c.volatility.get("regime"), volatility_percentile=c.volatility.get("percentile"),
            sessions=c.sessions, last_price=rnd(closes[-1], d), last_candle_close=c.last_candle_close,
            change_24h_pct=round(change, 3) if change is not None else None,
            spark=[rnd(x, d) or 0.0 for x in _spark(day or closes[-SPARK_POINTS:])],
            spark_from=datetime.fromtimestamp(last_t - (len(day) - 1) * tf_s, tz=now.tzinfo) if day else None,
        ))
    items.sort(key=lambda i: (LIGHT_ORDER.get(i.light, 9), -(i.volatility_percentile or -1.0), i.symbol))
    for rank, item in enumerate(items, start=1):
        item.rank = rank
    return RadarOut(timeframe=timeframe, as_of=now, items=items, ranking=RANKING, method=cond.METHOD)

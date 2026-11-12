"""Alert evaluation (worker): price/% move on each newly closed candle, signal alerts on each new signal, news
alerts every tick. A firing inserts an ``alert_events`` row (unique per alert + dedupe key, so re-running a
tick never duplicates), respects the alert's cooldown, and switches one-shot alerts off.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market import Instrument
from app.models.signals import Signal
from app.models.tools import Alert, AlertEvent, NewsEvent, Watchlist, WatchlistItem
from app.services.marketdata.candles import load_series, ts_to_dt
from app.services.news.guard import instrument_currencies
from ml.calibration.strength import NO_EDGE, TIER_ORDER
from ml.data.candles import interval_seconds

NFA = "Not financial advice."


def _fmt(x: float, decimals: int) -> str:
    return f"{x:.{decimals}f}"


async def fire(db: AsyncSession, alert: Alert, dedupe_key: str, title: str, body: str, data: dict[str, Any],
               now: datetime) -> int | None:
    """Record a firing unless the alert is cooling down or this trigger was already recorded."""
    if alert.last_triggered_at is not None and now < alert.last_triggered_at + timedelta(seconds=alert.cooldown_s):
        return None
    new_id = await db.scalar(pg_insert(AlertEvent).values(
        alert_id=alert.id, user_id=alert.user_id, kind=alert.kind, dedupe_key=dedupe_key[:120], title=title[:120],
        body=body, data=data, triggered_at=now).on_conflict_do_nothing().returning(AlertEvent.id))
    if new_id is None:
        return None
    alert.last_triggered_at = now
    alert.trigger_count += 1
    if not alert.recurring:
        alert.active = False
    return int(new_id)


async def on_candles(db: AsyncSession, instrument_id: int, listing_id: int, timeframe: str,
                     new_since: int, now: datetime) -> list[int]:
    """Price-cross and %-move alerts on the candles of (listing, timeframe) that opened after ``new_since`` and
    closed within the last two candles (min 15 min) of ``now``. Caller commits."""
    alerts = (await db.scalars(select(Alert).where(
        Alert.active, Alert.kind.in_(("price_cross", "pct_move")), Alert.instrument_id == instrument_id,
        Alert.timeframe == timeframe))).unique().all()
    if not alerts:
        return []
    instrument = await db.get(Instrument, instrument_id)
    assert instrument is not None
    window = max([int(a.params.get("window_candles", 1)) for a in alerts] + [1])
    tf_s = interval_seconds(timeframe)
    series = await load_series(db, listing_id, timeframe, 200 + window)
    # only candles that closed recently: after downtime or a backfill, old crossings are not news any more
    oldest = now.timestamp() - max(2 * tf_s, 900) - tf_s
    new_idx = [i for i, t in enumerate(series["time"]) if t > new_since and t >= oldest]
    fired: list[int] = []
    d = instrument.price_decimals
    for a in alerts:
        for i in new_idx:
            if not a.active:
                break
            c = series.iloc[i]
            close_at = ts_to_dt(int(c["time"]) + tf_s)
            data = {"symbol": instrument.symbol, "timeframe": timeframe, "price": float(c["close"]),
                    "candle_time": ts_to_dt(int(c["time"])).isoformat()}
            if a.kind == "price_cross" and i > 0:
                level, up = float(a.params["level"]), a.params["direction"] == "above"
                prev = float(series["close"].iloc[i - 1])
                crossed = (prev < level <= float(c["high"])) if up else (prev > level >= float(c["low"]))
                if crossed:
                    title = f"{instrument.symbol} {'above' if up else 'below'} {_fmt(level, d)}"
                    body = (f"{instrument.symbol} traded {'above' if up else 'below'} {_fmt(level, d)} "
                            f"({timeframe} candle closed {_fmt(float(c['close']), d)}). {NFA}")
                    ev = await fire(db, a, f"cross:{int(c['time'])}", title, body, data | {"level": level}, close_at)
                    fired += [ev] if ev else []
            elif a.kind == "pct_move" and i >= int(a.params["window_candles"]):
                ref = float(series["close"].iloc[i - int(a.params["window_candles"])])
                move = (float(c["close"]) / ref - 1) * 100
                want = a.params["direction"]
                hit = abs(move) >= float(a.params["pct"]) and (want == "either" or (want == "up") == (move > 0))
                if hit:
                    n = int(a.params["window_candles"])
                    title = f"{instrument.symbol} {move:+.2f}% in {n} x {timeframe}"
                    body = f"{instrument.symbol} moved {move:+.2f}% over the last {n} {timeframe} candles. {NFA}"
                    ev = await fire(db, a, f"move:{int(c['time'])}", title, body, data | {"move_pct": move},
                                    close_at)
                    fired += [ev] if ev else []
    return fired


async def _watchlist_instruments(db: AsyncSession, user_ids: Iterable[Any]) -> dict[int, set[int]]:
    """watchlist id -> instrument ids, for the given users' lists."""
    rows = (await db.execute(select(WatchlistItem.watchlist_id, WatchlistItem.instrument_id)
                             .join(Watchlist, Watchlist.id == WatchlistItem.watchlist_id)
                             .where(Watchlist.user_id.in_(list(user_ids))))).all()
    out: dict[int, set[int]] = {}
    for wl, inst in rows:
        out.setdefault(wl, set()).add(inst)
    return out


async def _scope(db: AsyncSession, alerts: list[Alert]) -> dict[int, set[int] | None]:
    """alert id -> instrument ids it covers (None = all instruments of the user's watchlists)."""
    lists = await _watchlist_instruments(db, {a.user_id for a in alerts})
    owners = dict((await db.execute(select(Watchlist.id, Watchlist.user_id))).all()) if lists else {}
    out: dict[int, set[int] | None] = {}
    for a in alerts:
        if a.instrument_id is not None:
            out[a.id] = {a.instrument_id}
        elif a.watchlist_id is not None:
            out[a.id] = lists.get(a.watchlist_id, set())
        else:
            out[a.id] = set().union(*(v for k, v in lists.items() if owners.get(k) == a.user_id)) if lists else set()
    return out


async def on_signals(db: AsyncSession, signal_ids: list[int], now: datetime) -> list[int]:
    """Signal alerts. Only earned strength tiers can meet a ``min_strength``; 'Very Weak - Wait' never alerts."""
    if not signal_ids:
        return []
    signals = [s for s in (await db.scalars(select(Signal).where(Signal.id.in_(signal_ids)))).unique().all()
               if s.strength != NO_EDGE and s.model_usable]
    if not signals:
        return []
    alerts = list((await db.scalars(select(Alert).where(Alert.active, Alert.kind == "signal"))).unique().all())
    scope = await _scope(db, alerts)
    fired: list[int] = []
    for s in signals:
        for a in alerts:
            if not a.active or s.instrument_id not in (scope.get(a.id) or set()):
                continue
            if a.timeframe and a.timeframe != s.timeframe:
                continue
            if a.params.get("horizons") and s.horizon not in a.params["horizons"]:
                continue
            if TIER_ORDER.index(s.strength) > TIER_ORDER.index(a.params["min_strength"]):
                continue
            sym = s.instrument.symbol
            title = f"{sym} {s.timeframe}: {s.direction.upper()} ({s.strength})"
            body = (f"{s.strength} signal: {sym} {s.direction} over the next {s.horizon} x {s.timeframe} candle(s), "
                    f"calibrated probability {s.confidence:.0%}. Check the live track record. {NFA}")
            ev = await fire(db, a, f"signal:{s.id}", title, body,
                            {"symbol": sym, "signal_id": s.id, "timeframe": s.timeframe}, now)
            fired += [ev] if ev else []
    return fired


async def news_tick(db: AsyncSession, now: datetime) -> list[int]:
    """News alerts: a relevant event starts within the alert's lead time."""
    alerts = list((await db.scalars(select(Alert).where(Alert.active, Alert.kind == "news"))).unique().all())
    if not alerts:
        return []
    max_lead = max(int(a.params.get("lead_minutes", 30)) for a in alerts)
    events = (await db.scalars(select(NewsEvent).where(
        NewsEvent.event_at > now, NewsEvent.event_at <= now + timedelta(minutes=max_lead),
        or_(NewsEvent.impact == "high", NewsEvent.impact == "medium")))).all()
    if not events:
        return []
    scope = await _scope(db, alerts)
    inst_ids = set().union(*(v or set() for v in scope.values()))
    instruments = {i.id: i for i in (await db.scalars(select(Instrument).where(Instrument.id.in_(inst_ids)))).all()}
    fired: list[int] = []
    for a in alerts:
        covered = [instruments[i] for i in sorted(scope.get(a.id) or set()) if i in instruments]
        cur: set[str] = set()
        for inst in covered:
            c, high_only = instrument_currencies(inst.asset_class, inst.base, inst.quote)
            cur |= {f"{x}:high" for x in c} | (set() if high_only else {f"{x}:medium" for x in c})
        lead = timedelta(minutes=int(a.params.get("lead_minutes", 30)))
        min_impact = a.params.get("min_impact", "high")
        for e in events:
            if e.event_at - now > lead or (min_impact == "high" and e.impact != "high"):
                continue
            if e.currency != "All" and f"{e.currency}:{e.impact}" not in cur:
                continue
            mins = max(1, round((e.event_at - now).total_seconds() / 60))
            title = f"{e.currency} {e.title} in {mins} min"
            body = (f"{e.impact.capitalize()}-impact event: {e.currency} {e.title} at "
                    f"{e.event_at.astimezone(UTC):%H:%M} UTC. Spreads can widen and price can gap. {NFA}")
            ev = await fire(db, a, f"news:{e.id}", title, body,
                            {"event_id": e.id, "currency": e.currency, "event_at": e.event_at.isoformat()}, now)
            fired += [ev] if ev else []
            if not a.active:
                break
    return fired

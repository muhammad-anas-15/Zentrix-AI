"""``GET /v1/candles/live``: the forming candle for live charts. Public, with its own IP rate-limit bucket because
charts poll it every few seconds."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select

from app.api.deps import DbDep, NowDep
from app.core.errors import AppError
from app.core.ratelimit import limit_by_ip
from app.models.market import Candle, Timeframe
from app.schemas.signals import CandleOut, LiveCandleOut
from app.services.marketdata.live import LiveCandles, is_live_venue, period_open
from app.services.marketdata.lookup import listing_for
from ml.data.candles import interval_seconds
from ml.data.sessions import is_market_open

router = APIRouter(tags=["market"], dependencies=[Depends(limit_by_ip("live", "rate_limit_live"))])
LIVE_POLL_S = 2
RETRY_POLL_S = 10
MAX_POLL_S = 60
CLOSE_GRACE_S = 8  # the worker stores a closed candle a few seconds after the close


def _out(row: dict[str, float]) -> CandleOut:
    return CandleOut(t=datetime.fromtimestamp(row["time"], tz=UTC), o=row["open"], h=row["high"], l=row["low"],
                     c=row["close"], v=row.get("volume"))


def _live(request: Request) -> LiveCandles:
    live: LiveCandles | None = getattr(request.app.state, "live_candles", None)
    if live is None:
        settings = request.app.state.settings
        live = LiveCandles(settings.live_candle_cache_s, request.app.state.clock)
        request.app.state.live_candles = live
    return live


@router.get("/candles/live", response_model=LiveCandleOut,
            summary="Forming candle for live charts (real time on exchange feeds, closed candles otherwise)")
async def live_candle(
    request: Request, db: DbDep, now: NowDep,
    symbol: Annotated[str, Query(min_length=3, max_length=40, description="Canonical symbol, e.g. BTC/USDT")],
    timeframe: Annotated[str, Query(max_length=8)] = "15m",
    venue: Annotated[str | None, Query(max_length=32)] = None,
) -> LiveCandleOut:
    if await db.scalar(select(Timeframe.code).where(Timeframe.code == timeframe)) is None:
        raise AppError(422, "unknown_timeframe", f"Unknown timeframe {timeframe}")
    ref = await listing_for(db, symbol, venue)
    tf_s = interval_seconds(timeframe)
    now_ts = now.timestamp()
    current = period_open(now_ts, tf_s)
    market_open = is_market_open(current, ref.instrument.session)
    base: dict[str, Any] = {"symbol": symbol, "venue": ref.venue, "timeframe": timeframe, "server_time": now,
                            "market_open": market_open}

    note = None
    if is_live_venue(ref.venue, timeframe):
        rows = await _live(request).get(ref.venue, ref.listing.venue_symbol, timeframe)
        if rows:
            forming = [r for r in rows if r["time"] + tf_s > now_ts]
            closed = [r for r in rows if r["time"] + tf_s <= now_ts]
            head = forming[-1] if forming else rows[-1]
            return LiveCandleOut(**base, live=True, candle=_out(head), forming=bool(forming),
                                 closed=_out(closed[-1]) if closed else None,
                                 closes_at=datetime.fromtimestamp(head["time"] + tf_s, tz=UTC),
                                 poll_s=LIVE_POLL_S, source=ref.venue)
        note = "Live feed unreachable right now; showing the last stored candle."

    last = await db.scalar(select(Candle).where(Candle.listing_id == ref.listing.id, Candle.timeframe == timeframe)
                           .order_by(Candle.ts.desc()).limit(1))
    closes_at = datetime.fromtimestamp(current + tf_s, tz=UTC) if market_open else None
    if note is None:
        note = "This market's data feed delivers closed candles only: the chart updates when each candle closes."
    if closes_at is not None:
        wait = int((closes_at - now).total_seconds()) + CLOSE_GRACE_S
        poll = RETRY_POLL_S if note.startswith("Live feed") else max(5, min(MAX_POLL_S, wait))
    else:
        poll = MAX_POLL_S
    return LiveCandleOut(**base, live=False, forming=False, closed=None, closes_at=closes_at, poll_s=poll,
                         source="stored", note=note,
                         candle=CandleOut(t=last.ts, o=last.open, h=last.high, l=last.low, c=last.close,
                                          v=last.volume) if last is not None else None)

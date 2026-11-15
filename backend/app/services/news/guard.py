"""News guard: is a scheduled high-impact event close enough to an instrument to stay out?

States (worst first): ``blackout`` (inside a high-impact event's window), ``caution`` (inside a medium-impact
window, or a high-impact event is coming soon), ``clear``, ``unknown`` (calendar missing or stale: never
reported as clear). Events reach an instrument through its currencies: FX base and quote; metals,
commodities and indices their quote currency (USD); crypto only high-impact USD events. "All" events
(e.g. G7) reach everything. Rules only; this does not predict how price reacts.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.tools import NewsEvent

STATE_ORDER = ("blackout", "unknown", "caution", "clear")


class EventLike(Protocol):
    @property
    def title(self) -> str: ...
    @property
    def currency(self) -> str: ...
    @property
    def impact(self) -> str: ...
    @property
    def event_at(self) -> datetime: ...


@dataclass(frozen=True)
class GuardConfig:
    blackout_before_s: int = 1800
    blackout_after_s: int = 1800
    medium_window_s: int = 900
    high_lead_s: int = 7200
    stale_after_s: int = 6 * 3600

    @classmethod
    def from_settings(cls, s: Settings) -> GuardConfig:
        return cls(s.news_blackout_before_s, s.news_blackout_after_s, s.news_medium_window_s, s.news_high_lead_s,
                   s.news_stale_after_s)


@dataclass
class GuardResult:
    state: str
    reasons: list[str] = field(default_factory=list)
    active: list[dict[str, Any]] = field(default_factory=list)  # events causing blackout/caution now
    next_event: dict[str, Any] | None = None
    countdown_s: int | None = None
    blackout_until: datetime | None = None
    currencies: list[str] = field(default_factory=list)
    calendar_updated_at: datetime | None = None


def instrument_currencies(asset_class: str, base: str, quote: str) -> tuple[frozenset[str], bool]:
    """(calendar currencies that affect the instrument, high-impact only?)."""
    if asset_class == "fx":
        return frozenset({base, quote}), False
    if asset_class == "crypto":
        return frozenset({"USD"}), True
    return frozenset({quote if quote != "USDT" else "USD"}), False


def event_dict(e: EventLike, now: datetime) -> dict[str, Any]:
    return {"title": e.title, "currency": e.currency, "impact": e.impact, "event_at": e.event_at,
            "in_s": int((e.event_at - now).total_seconds())}


def evaluate_guard(events: Sequence[EventLike], currencies: frozenset[str], high_only: bool, now: datetime,
                   cfg: GuardConfig, calendar_updated_at: datetime | None) -> GuardResult:
    relevant = sorted((e for e in events if (e.currency in currencies or e.currency == "All")
                       and (e.impact == "high" or (e.impact == "medium" and not high_only))),
                      key=lambda e: e.event_at)
    res = GuardResult("clear", currencies=sorted(currencies), calendar_updated_at=calendar_updated_at)
    for e in relevant:
        dt = (e.event_at - now).total_seconds()
        label = f"{e.currency} {e.title} ({e.impact})"
        if e.impact == "high" and -cfg.blackout_after_s <= dt <= cfg.blackout_before_s:
            res.state = "blackout"
            until = e.event_at + timedelta(seconds=cfg.blackout_after_s)
            res.blackout_until = max(res.blackout_until or until, until)
            res.reasons.append(f"{label} {_when(dt)}: stay out from {cfg.blackout_before_s // 60} min before to "
                               f"{cfg.blackout_after_s // 60} min after")
            res.active.append(event_dict(e, now))
        elif ((e.impact == "medium" and abs(dt) <= cfg.medium_window_s)
              or (e.impact == "high" and cfg.blackout_before_s < dt <= cfg.high_lead_s)):
            res.state = _worst(res.state, "caution")
            res.reasons.append(f"{label} {_when(dt)}")
            res.active.append(event_dict(e, now))
    upcoming = [e for e in relevant if e.event_at > now]
    if upcoming:
        res.next_event = event_dict(upcoming[0], now)
        res.countdown_s = res.next_event["in_s"]
    fresh = calendar_updated_at is not None and (now - calendar_updated_at).total_seconds() <= cfg.stale_after_s
    if not fresh:
        res.reasons.append("economic calendar unavailable or out of date: news risk unknown")
        res.state = _worst(res.state, "unknown")
    elif res.state == "clear":
        res.reasons.append("no relevant high/medium-impact event nearby")
    return res


def _worst(a: str, b: str) -> str:
    return a if STATE_ORDER.index(a) <= STATE_ORDER.index(b) else b


def _when(dt: float) -> str:
    m = round(abs(dt) / 60)
    return f"in {m} min" if dt > 0 else ("now" if m == 0 else f"{m} min ago")


async def calendar_updated_at(db: AsyncSession) -> datetime | None:
    return await db.scalar(select(func.max(NewsEvent.fetched_at)))


async def load_events(db: AsyncSession, currencies: frozenset[str] | None, start: datetime, end: datetime,
                      impacts: Sequence[str] = ("high", "medium"), limit: int = 500) -> list[NewsEvent]:
    stmt = select(NewsEvent).where(NewsEvent.event_at >= start, NewsEvent.event_at <= end,
                                   NewsEvent.impact.in_(impacts))
    if currencies is not None:
        stmt = stmt.where(NewsEvent.currency.in_([*currencies, "All"]))
    return list((await db.scalars(stmt.order_by(NewsEvent.event_at).limit(limit))).all())


async def guard_for(db: AsyncSession, asset_class: str, base: str, quote: str, now: datetime,
                    cfg: GuardConfig) -> GuardResult:
    currencies, high_only = instrument_currencies(asset_class, base, quote)
    events = await load_events(db, currencies, now - timedelta(seconds=max(cfg.blackout_after_s,
                                                                         cfg.medium_window_s)),
                               now + timedelta(days=8))
    return evaluate_guard(events, currencies, high_only, now, cfg, await calendar_updated_at(db))

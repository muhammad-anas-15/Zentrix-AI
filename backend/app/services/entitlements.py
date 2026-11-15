"""Plans and entitlements: the feature registry and who may use what.

One table of product features (free or premium) drives the gates (``app/api/premium.py``), the "Premium" labels
in responses, ``GET /v1/plans`` and the docs. Billing is not integrated. While ``PREMIUM_ENFORCED=false`` every
feature is open to everyone; :func:`resolve_access` still reports each user's real plan so the app can show it.

A user has premium when any of these holds now:
  * ``users.plan = 'premium'`` and ``plan_expires_at`` is empty or in the future (set by an admin; later billing),
  * a ``subscriptions`` row is ``active``/``grace`` and not expired (written by billing, later),
  * an ``entitlements`` grant with key ``premium`` is active.
A grant whose key is one premium feature unlocks only that feature (e.g. a trial of the scenario path).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from sqlalchemy import ColumnElement, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.market import Instrument
from app.models.signals import Signal, SignalOutcome
from app.models.user import Entitlement, Subscription, User

Tier = Literal["free", "premium"]
Source = Literal["plan", "subscription", "grant"]
PREMIUM = "premium"  # entitlement key that unlocks every premium feature
ACTIVE_SUBSCRIPTION = ("active", "grace")


@dataclass(frozen=True)
class Feature:
    key: str
    tier: Tier
    title: str
    description: str


FEATURES: dict[str, Feature] = {f.key: f for f in [
    Feature("market_conditions", "free", "Market-condition light",
            "Trend/range, volatility, session, news and data freshness as a green/amber/red light."),
    Feature("news_guard", "free", "News guard",
            "Economic calendar, blackout/caution per instrument and a countdown to the next event."),
    Feature("position_size", "free", "Position-size calculator",
            "Size, money at risk, pip value, R:R and margin, with warnings."),
    Feature("track_record", "free", "Public track record",
            "Every signal with its outcome, live accuracy stats and the models behind them."),
    Feature("free_signals", "free", "Signals on the free markets",
            "Live signals for the free markets (see free_markets)."),
    Feature("watchlists", "free", "Watchlists",
            "Lists of instruments with last closed price, 24h change and news state."),
    Feature("price_alerts", "free", "Price, move and news alerts",
            "Push and inbox alerts for price crosses, % moves and upcoming news."),
    Feature("risk_profile", "free", "Risk profile", "Account currency, balance and your risk rules."),
    Feature("all_markets", "premium", "All markets and timeframes",
            "Live signals for every instrument and timeframe, in the API and on the live stream."),
    Feature("signal_alerts", "premium", "Signal alerts",
            "Push alerts when an earned signal strength appears on your instruments or watchlist."),
    Feature("trade_levels", "premium", "Stop-loss and take-profit levels",
            "ATR-based stop and targets per signal or instrument, with their historical base rate."),
    Feature("exit_advisor", "premium", "Exit advisor",
            "Hold / tighten stop / take partial / consider exit for an open position."),
    Feature("scenario", "premium", "Scenario path",
            "Price bands for the next 1-5 candles with their measured coverage."),
    Feature("pattern_outlook", "premium", "Pattern projection",
            "The candlestick pattern now and what followed it over 1-5 candles in this market's history."),
    Feature("journal", "premium", "Trade journal and review",
            "Journal with server-computed P&L and R, statistics and a review of your habits."),
    Feature("risk_guard", "premium", "Daily risk guard",
            "Daily-loss-limit, overtrading, loss-streak and quick re-entry warnings."),
]}
PREMIUM_FEATURES = tuple(k for k, f in FEATURES.items() if f.tier == "premium")
GRANT_KEYS = (PREMIUM, *PREMIUM_FEATURES)


def _later(a: datetime | None, b: datetime | None) -> datetime | None:
    """The later of two end times, where None means open-ended."""
    return None if a is None or b is None else max(a, b)


@dataclass(frozen=True)
class Access:
    """What a user is entitled to now. Independent of PREMIUM_ENFORCED (the gate combines the two)."""

    source: Source | None = None  # why the user has premium; None = free
    premium_until: datetime | None = None  # end of that premium (None = open-ended, or free)
    feature_grants: dict[str, datetime | None] = field(default_factory=dict)  # single-feature grant -> its end

    @property
    def premium(self) -> bool:
        return self.source is not None

    @property
    def plan(self) -> Literal["free", "premium"]:
        return "premium" if self.premium else "free"

    def has(self, feature: str) -> bool:
        return FEATURES[feature].tier == "free" or self.premium or feature in self.feature_grants


FREE_ACCESS = Access()


async def resolve_access(db: AsyncSession, user: User, now: datetime) -> Access:
    sources: list[tuple[Source, datetime | None]] = []
    if user.plan == PREMIUM and (user.plan_expires_at is None or user.plan_expires_at > now):
        sources.append(("plan", user.plan_expires_at))
    subs = (await db.scalars(select(Subscription).where(
        Subscription.user_id == user.id, Subscription.status.in_(ACTIVE_SUBSCRIPTION), Subscription.started_at <= now,
        or_(Subscription.expires_at.is_(None), Subscription.expires_at > now)))).all()
    sources += [("subscription", s.expires_at) for s in subs]
    grants = (await db.scalars(select(Entitlement).where(
        Entitlement.user_id == user.id, Entitlement.key.in_(GRANT_KEYS), Entitlement.starts_at <= now,
        or_(Entitlement.ends_at.is_(None), Entitlement.ends_at > now)))).all()
    features: dict[str, datetime | None] = {}
    for g in grants:
        if g.key == PREMIUM:
            sources.append(("grant", g.ends_at))
        else:
            features[g.key] = _later(features[g.key], g.ends_at) if g.key in features else g.ends_at
    if not sources:
        return Access(feature_grants=features)
    until = sources[0][1]
    for _, end in sources[1:]:
        until = _later(until, end)
    return Access(source=sources[0][0], premium_until=until, feature_grants=features)


async def users_with_feature(db: AsyncSession, user_ids: Iterable[uuid.UUID], feature: str,
                             now: datetime) -> set[uuid.UUID]:
    """Bulk check for the worker: which of these users may use ``feature`` now (ignores PREMIUM_ENFORCED)."""
    ids = set(user_ids)
    if not ids or FEATURES[feature].tier == "free":
        return ids
    by_plan = await db.scalars(select(User.id).where(
        User.id.in_(ids), User.plan == PREMIUM, or_(User.plan_expires_at.is_(None), User.plan_expires_at > now)))
    by_sub = await db.scalars(select(Subscription.user_id).where(
        Subscription.user_id.in_(ids), Subscription.status.in_(ACTIVE_SUBSCRIPTION), Subscription.started_at <= now,
        or_(Subscription.expires_at.is_(None), Subscription.expires_at > now)))
    by_grant = await db.scalars(select(Entitlement.user_id).where(
        Entitlement.user_id.in_(ids), Entitlement.key.in_((PREMIUM, feature)), Entitlement.starts_at <= now,
        or_(Entitlement.ends_at.is_(None), Entitlement.ends_at > now)))
    return set(by_plan.all()) | set(by_sub.all()) | set(by_grant.all())


def is_free_market(settings: Settings, symbol: str, timeframe: str) -> bool:
    return symbol in settings.free_signal_symbols and timeframe in settings.free_signal_timeframes


def visible_signals(settings: Settings) -> ColumnElement[bool]:
    """Signals a viewer without ``all_markets`` may see: the free markets, plus every resolved signal, so the public
    track record stays complete (only live, unresolved signals of premium markets are withheld)."""
    free = and_(Signal.instrument_id.in_(select(Instrument.id).where(
        Instrument.symbol.in_(settings.free_signal_symbols))), Signal.timeframe.in_(settings.free_signal_timeframes))
    resolved = select(SignalOutcome.signal_id).where(SignalOutcome.signal_id == Signal.id).exists()
    return or_(free, resolved)

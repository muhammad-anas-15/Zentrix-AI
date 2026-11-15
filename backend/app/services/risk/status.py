"""Daily risk status from the user's risk profile and journal: loss limit, overtrading, loss streak and
quick re-entry after a loss. "Today" is the user's calendar day in their timezone."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tools import JournalEntry, RiskProfile
from app.models.user import User

REVENGE_WINDOW = timedelta(minutes=15)


@dataclass(frozen=True)
class ProfileValues:
    account_currency: str = "USD"
    balance: float | None = None
    risk_per_trade_pct: float = 1.0
    max_daily_loss_pct: float = 3.0
    max_trades_per_day: int = 6
    max_consecutive_losses: int = 3
    leverage: float | None = None
    is_default: bool = True


async def profile_values(db: AsyncSession, user: User) -> ProfileValues:
    p = await db.get(RiskProfile, user.id)
    if p is None:
        return ProfileValues()
    return ProfileValues(p.account_currency, p.balance, p.risk_per_trade_pct, p.max_daily_loss_pct,
                         p.max_trades_per_day, p.max_consecutive_losses, p.leverage, False)


def user_tz(user: User) -> ZoneInfo:
    try:
        return ZoneInfo(user.timezone or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def day_window(now: datetime, tz: ZoneInfo) -> tuple[datetime, datetime]:
    local = now.astimezone(tz)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


async def risk_status(db: AsyncSession, user: User, now: datetime) -> dict[str, Any]:
    pv = await profile_values(db, user)
    tz = user_tz(user)
    start, end = day_window(now, tz)
    rows = list((await db.scalars(select(JournalEntry).where(
        JournalEntry.user_id == user.id,
        or_(JournalEntry.entry_at >= start - timedelta(days=7), JournalEntry.exit_at.is_(None)))
        .order_by(JournalEntry.entry_at))).all())
    mine = [e for e in rows if e.account_currency == pv.account_currency]
    closed_today = [e for e in mine if e.exit_at is not None and start <= e.exit_at < end]
    realized = sum(e.pnl_account or 0.0 for e in closed_today)
    opened_today = [e for e in rows if start <= e.entry_at < end]
    open_pos = [e for e in mine if e.exit_at is None]
    open_risk = sum(e.risk_account or 0.0 for e in open_pos)
    closed = sorted((e for e in mine if e.exit_at is not None), key=lambda e: e.exit_at)  # type: ignore[arg-type,return-value]
    streak = 0
    for e in reversed(closed):
        if (e.pnl_account or 0) < 0:
            streak += 1
        else:
            break
    last_loss = next((e for e in reversed(closed) if (e.pnl_account or 0) < 0), None)

    limit = pv.balance * pv.max_daily_loss_pct / 100 if pv.balance else None
    used = max(-realized, 0.0)
    left = limit - used if limit is not None else None
    warnings: list[dict[str, str]] = []
    level = "ok"

    def warn(code: str, message: str, stop: bool = False) -> None:
        nonlocal level
        warnings.append({"code": code, "message": message})
        level = "stop" if stop or level == "stop" else "warning"

    if limit is not None and used >= limit:
        warn("daily_loss_limit_reached", f"Today's loss ({used:.2f}) reached your limit ({limit:.2f} = "
             f"{pv.max_daily_loss_pct:g}% of balance). Consider stopping for today.", stop=True)
    elif limit is not None and used >= 0.8 * limit:
        warn("daily_loss_limit_near", f"Today's loss ({used:.2f}) is {used / limit:.0%} of your daily limit.")
    if left is not None and open_risk > 0 and open_risk > max(left, 0):
        warn("open_risk_exceeds_limit", f"If open trades hit their stops ({open_risk:.2f}), you would pass "
             "today's loss limit.")
    if len(opened_today) >= pv.max_trades_per_day:
        warn("overtrading", f"{len(opened_today)} trades today (your maximum is {pv.max_trades_per_day}).")
    if streak >= pv.max_consecutive_losses:
        warn("loss_streak", f"{streak} losing trades in a row. A pause usually helps more than the next trade.")
    if last_loss is not None and last_loss.exit_at is not None and now - last_loss.exit_at <= REVENGE_WINDOW:
        mins = int((now - last_loss.exit_at).total_seconds() // 60)
        warn("recent_loss", f"Your last trade closed at a loss {mins} min ago. Make sure the next trade is a "
             "plan, not a reaction.")
    return {
        "level": level, "warnings": warnings, "day_start": start, "timezone": str(tz),
        "account_currency": pv.account_currency, "realized_pnl_today": realized, "daily_loss_limit": limit,
        "daily_loss_used": used, "daily_loss_left": left, "trades_today": len(opened_today),
        "max_trades_per_day": pv.max_trades_per_day, "open_positions": len(open_pos), "open_risk": open_risk,
        "consecutive_losses": streak, "profile_is_default": pv.is_default,
        "excluded_other_currency": len(rows) - len(mine),
    }

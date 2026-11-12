"""Trade journal: server-side P&L and R multiple, statistics and a rule-based review of the user's own trades.

P&L in quote currency = (exit - entry) x quantity (x -1 for shorts). Account-currency P&L uses the client's
``fx_rate`` or the stored quote->account rate at exit, minus fees. R multiple = price move / stop distance
(currency-free; fees excluded). Statistics only use closed trades in the requested account currency.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tools import JournalEntry, NewsEvent
from app.services.news.guard import instrument_currencies
from app.services.risk.conversion import ConversionUnavailable, quote_to_account

REVENGE_WINDOW = timedelta(minutes=15)
MIN_REVIEW_TRADES = 5


def sign(side: str) -> int:
    return 1 if side == "long" else -1


async def recompute(db: AsyncSession, e: JournalEntry, fx_rate: float | None) -> list[str]:
    """Fill fx_rate, risk_account, pnl_quote, pnl_account and r_multiple. Returns notes for the client."""
    notes: list[str] = []
    quote = e.instrument.quote
    rate = fx_rate
    if rate is None:
        try:
            r = await quote_to_account(db, quote, e.account_currency, e.exit_at or e.entry_at)
            rate, notes = r.rate, r.notes
        except ConversionUnavailable as exc:
            notes.append(str(exc))
    e.fx_rate = rate
    dist = abs(e.entry_price - e.stop_loss) if e.stop_loss is not None else None
    e.risk_account = dist * e.quantity * rate if dist and rate is not None else None
    if e.exit_price is None:
        e.pnl_quote = e.pnl_account = e.r_multiple = None
        return notes
    move = (e.exit_price - e.entry_price) * sign(e.side)
    e.pnl_quote = move * e.quantity
    e.pnl_account = e.pnl_quote * rate - (e.fees or 0.0) if rate is not None else None
    e.r_multiple = move / dist if dist else None
    return notes


def _result(e: JournalEntry) -> float | None:
    return e.pnl_account if e.pnl_account is not None else e.pnl_quote


def compute_stats(entries: list[JournalEntry], account_currency: str) -> dict[str, Any]:
    closed = [e for e in entries if e.exit_at is not None]
    mine = [e for e in closed if e.account_currency == account_currency and e.pnl_account is not None]
    pnls = [e.pnl_account for e in mine if e.pnl_account is not None]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    rs = [e.r_multiple for e in mine if e.r_multiple is not None]
    by_inst: dict[str, list[float]] = defaultdict(list)
    for e in mine:
        by_inst[e.instrument.symbol].append(e.pnl_account or 0.0)
    streak = worst = 0
    for e in sorted(mine, key=lambda x: x.exit_at or x.entry_at):
        streak = streak + 1 if (e.pnl_account or 0) < 0 else 0
        worst = max(worst, streak)
    gross_loss = -sum(losses)
    return {
        "account_currency": account_currency,
        "trades": len(entries), "open": len(entries) - len(closed), "closed": len(closed),
        "counted": len(mine), "excluded": len(closed) - len(mine),
        "wins": len(wins), "losses": len(losses), "breakeven": len(pnls) - len(wins) - len(losses),
        "win_rate": len(wins) / (len(wins) + len(losses)) if wins or losses else None,
        "net_pnl": sum(pnls), "avg_win": statistics.fmean(wins) if wins else None,
        "avg_loss": statistics.fmean(losses) if losses else None,
        "profit_factor": sum(wins) / gross_loss if gross_loss > 0 else None,
        "expectancy": statistics.fmean(pnls) if pnls else None,
        "avg_r": statistics.fmean(rs) if rs else None, "max_consecutive_losses": worst,
        "by_instrument": [{"symbol": s, "trades": len(v), "net_pnl": sum(v)}
                          for s, v in sorted(by_inst.items(), key=lambda kv: sum(kv[1]))],
    }


def _hold(e: JournalEntry) -> float:
    assert e.exit_at is not None
    return (e.exit_at - e.entry_at).total_seconds()


async def _blackout_entries(db: AsyncSession, entries: list[JournalEntry], before: timedelta,
                            after: timedelta) -> list[JournalEntry]:
    if not entries:
        return []
    start = min(e.entry_at for e in entries) - before
    end = max(e.entry_at for e in entries) + after
    events = (await db.scalars(select(NewsEvent).where(NewsEvent.impact == "high", NewsEvent.event_at >= start,
                                                       NewsEvent.event_at <= end + before))).all()
    out = []
    for e in entries:
        inst = e.instrument
        cur, _ = instrument_currencies(inst.asset_class, inst.base, inst.quote)
        if any((ev.currency in cur or ev.currency == "All") and ev.event_at - before <= e.entry_at <= ev.event_at
               + after for ev in events):
            out.append(e)
    return out


async def review(db: AsyncSession, entries: list[JournalEntry], account_currency: str,
                 max_trades_per_day: int, tz: Any, blackout: tuple[int, int] = (1800, 1800)) -> dict[str, Any]:
    """Rule-based observations about the user's own closed trades (facts from their journal, not advice)."""
    closed = sorted((e for e in entries if e.exit_at is not None and e.account_currency == account_currency),
                    key=lambda e: e.entry_at)
    if len(closed) < MIN_REVIEW_TRADES:
        return {"trades_reviewed": len(closed), "insights": [],
                "note": f"Add at least {MIN_REVIEW_TRADES} closed trades for a review."}
    insights: list[dict[str, Any]] = []

    def add(code: str, severity: str, message: str, **evidence: Any) -> None:
        insights.append({"code": code, "severity": severity, "message": message, "evidence": evidence})

    winners = [e for e in closed if (_result(e) or 0) > 0]
    losers = [e for e in closed if (_result(e) or 0) < 0]
    if winners and losers:
        hw, hl = statistics.fmean(map(_hold, winners)), statistics.fmean(map(_hold, losers))
        if hl > 1.5 * hw:
            add("losers_held_longer", "warning",
                f"You hold losing trades {hl / hw:.1f}x longer than winning trades on average.",
                avg_hold_winners_min=round(hw / 60, 1), avg_hold_losers_min=round(hl / 60, 1))
    no_stop = [e for e in closed if e.stop_loss is None]
    if len(no_stop) / len(closed) > 0.3:
        add("missing_stops", "warning", f"{len(no_stop)} of {len(closed)} trades had no stop-loss recorded.",
            trades_without_stop=len(no_stop))
    risks = [e.risk_account for e in closed if e.risk_account]
    if len(risks) >= MIN_REVIEW_TRADES and statistics.fmean(risks) > 0:
        cv = statistics.pstdev(risks) / statistics.fmean(risks)
        if cv > 0.5:
            add("inconsistent_risk", "warning",
                f"Money at risk per trade varies a lot (from {min(risks):.2f} to {max(risks):.2f} "
                f"{account_currency}).", coefficient_of_variation=round(cv, 2))
    win_r = [e.r_multiple for e in winners if e.r_multiple is not None]
    loss_r = [e.r_multiple for e in losers if e.r_multiple is not None]
    if win_r and loss_r and statistics.fmean(win_r) < 1 <= -statistics.fmean(loss_r):
        add("small_winners", "info",
            f"Average winner is {statistics.fmean(win_r):.2f}R while average loser is "
            f"{statistics.fmean(loss_r):.2f}R: winners are closed before the stop distance is earned.",
            avg_win_r=round(statistics.fmean(win_r), 2), avg_loss_r=round(statistics.fmean(loss_r), 2))
    news_trades = await _blackout_entries(db, closed, timedelta(seconds=blackout[0]), timedelta(seconds=blackout[1]))
    if news_trades:
        pnl = sum(_result(e) or 0 for e in news_trades)
        add("news_blackout_trades", "warning",
            f"{len(news_trades)} trades were opened inside a high-impact news window (net {pnl:.2f}).",
            trades=len(news_trades), net_pnl=round(pnl, 2))
    per_day: dict[Any, list[JournalEntry]] = defaultdict(list)
    for e in closed:
        per_day[e.entry_at.astimezone(tz).date()].append(e)
    busy = {d: v for d, v in per_day.items() if len(v) > max_trades_per_day}
    if busy:
        pnl = sum(_result(e) or 0 for v in busy.values() for e in v)
        add("overtrading_days", "warning",
            f"On {len(busy)} day(s) you took more than {max_trades_per_day} trades (net {pnl:.2f} on those days).",
            days=len(busy), net_pnl=round(pnl, 2))
    revenge = [b for a, b in zip(closed, closed[1:], strict=False)
               if (_result(a) or 0) < 0 and a.exit_at is not None and timedelta(0) <= b.entry_at - a.exit_at
               <= REVENGE_WINDOW]
    if revenge:
        won = sum(1 for e in revenge if (_result(e) or 0) > 0)
        add("quick_reentry_after_loss", "warning",
            f"{len(revenge)} trades were opened within 15 minutes of closing a loss; {won} of them won.",
            trades=len(revenge), wins=won)
    return {"trades_reviewed": len(closed), "insights": insights,
            "note": "Observations from your own journal. Not financial advice."}

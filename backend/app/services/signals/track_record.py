"""Live track record: computed from the signals and signal_outcomes tables only (never from backtests).

Hit rate = wins / (wins + losses); flat and void outcomes are counted but excluded, as in the ML report.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market import Instrument
from app.models.signals import Signal, SignalOutcome
from ml.calibration.strength import TIER_ORDER, wilson_interval


@dataclass(frozen=True)
class Filters:
    symbol: str | None = None
    timeframe: str | None = None
    horizon: int | None = None
    since: datetime | None = None
    model_version_id: int | None = None

    def cache_key(self) -> str:
        return "|".join(str(v) for v in (self.symbol, self.timeframe, self.horizon,
                                          self.since.isoformat() if self.since else None, self.model_version_id))


def summarize_counts(wins: int, losses: int, flats: int, voids: int, pending: int) -> dict[str, Any]:
    decided = wins + losses
    lo, hi = wilson_interval(wins, decided) if decided else (None, None)
    return {"signals": wins + losses + flats + voids + pending, "pending": pending,
            "wins": wins, "losses": losses, "flats": flats, "voids": voids, "decided": decided,
            "hit_rate": wins / decided if decided else None, "ci95": [lo, hi] if decided else None}


async def compute_track_record(db: AsyncSession, f: Filters) -> dict[str, Any]:
    outcome = SignalOutcome.outcome
    stmt = (select(
        Signal.strength,
        func.count(case((outcome == "win", 1))), func.count(case((outcome == "loss", 1))),
        func.count(case((outcome == "flat", 1))), func.count(case((outcome == "void", 1))),
        func.count(case((outcome.is_(None), 1))), func.min(Signal.created_at), func.max(Signal.created_at))
        .select_from(Signal).join(Instrument, Instrument.id == Signal.instrument_id)
        .outerjoin(SignalOutcome, SignalOutcome.signal_id == Signal.id).group_by(Signal.strength))
    if f.symbol:
        stmt = stmt.where(Instrument.symbol == f.symbol)
    if f.timeframe:
        stmt = stmt.where(Signal.timeframe == f.timeframe)
    if f.horizon:
        stmt = stmt.where(Signal.horizon == f.horizon)
    if f.since:
        stmt = stmt.where(Signal.created_at >= f.since)
    if f.model_version_id:
        stmt = stmt.where(Signal.model_version_id == f.model_version_id)
    rows: list[Any] = list((await db.execute(stmt)).all())  # (strength, win, loss, flat, void, pending, first, last)

    by_strength = {r[0]: summarize_counts(r[1], r[2], r[3], r[4], r[5]) for r in rows}
    totals = [sum(int(r[i]) for r in rows) for i in range(1, 6)]
    firsts = [r[6] for r in rows if r[6]]
    lasts = [r[7] for r in rows if r[7]]
    return {
        "overall": summarize_counts(*totals),
        "by_strength": [{"strength": t, **by_strength[t]} for t in TIER_ORDER if t in by_strength],
        "first_signal_at": min(firsts) if firsts else None,
        "last_signal_at": max(lasts) if lasts else None,
    }

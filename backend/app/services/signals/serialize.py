"""Signal -> API dict (also stored in the latest-signal cache)."""

from __future__ import annotations

from typing import Any

from app.models.signals import Signal


def signal_to_dict(s: Signal) -> dict[str, Any]:
    o = s.outcome
    tier_stats = (s.model_version.strength or {}).get("tier_stats", {}).get(s.strength)
    return {
        "id": s.id,
        "symbol": s.instrument.symbol,
        "venue": s.listing.venue.code,
        "timeframe": s.timeframe,
        "horizon": s.horizon,
        "candle_time": s.candle_ts.isoformat(),
        "decision_at": s.decision_at.isoformat(),
        "created_at": s.created_at.isoformat(),
        "direction": s.direction,
        "confidence": s.confidence,
        "p_up": s.p_up,
        "strength": s.strength,
        "model": {"key": s.model_version.key, "trained_at": s.model_version.trained_at.isoformat(),
                  "has_demonstrated_edge": s.model_usable},
        # Out-of-sample backtest hit rate of this strength tier for this model (labelled as backtest in the UI).
        "backtest_tier": tier_stats,
        "outcome": None if o is None else {
            "outcome": o.outcome, "entry_time": o.entry_ts.isoformat() if o.entry_ts else None,
            "entry_price": o.entry_price, "exit_time": o.exit_ts.isoformat() if o.exit_ts else None,
            "exit_price": o.exit_price, "move_pct": o.move_pct, "resolved_at": o.resolved_at.isoformat(),
            "note": o.note,
        },
    }

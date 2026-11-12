"""Per-candle-close signal job.

For a series (listing, timeframe) whose newest closed candle just arrived, every active model on that series
predicts from features built exactly as in training (stored market-hours candles + closed higher-timeframe
candles). A signal is stored only if this happens within ``max_lag`` of the candle's close: backfilled or late
candles never produce signals, so the track record contains no hindsight.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.signals import ModelVersion, Signal
from app.services.marketdata.candles import load_series, ts_to_dt
from app.services.signals.registry import ModelDriftError, PredictorCache
from ml.data.candles import interval_seconds
from ml.features.builder import INFERENCE_HTF_LOOKBACK, INFERENCE_LOOKBACK, NUMERIC_FEATURES
from ml.inference.features import InsufficientData, latest_feature_row

log = get_logger(__name__)
STORED_FEATURES = (*NUMERIC_FEATURES, "current_price", "resistance", "support", "pattern", "prev1")


@dataclass(frozen=True)
class SignalResult:
    created: list[int]
    skipped: list[str]


def _jsonable(features: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k in STORED_FEATURES:
        v = features.get(k)
        if isinstance(v, float) and not math.isfinite(v):
            v = None
        out[k] = v
    return out


async def generate_signals(db: AsyncSession, predictors: PredictorCache, listing_id: int, instrument_id: int,
                           timeframe: str, candle_ts: int, now: float, max_lag_s: int | None = None,
                           stale_htf: frozenset[str] = frozenset()) -> SignalResult:
    """Signals for the closed candle opening at ``candle_ts``. Idempotent (unique per model version + candle).
    ``stale_htf``: higher timeframes whose ingestion failed this round; dependent models are skipped rather
    than predicting from an out-of-date trend feature. Caller commits."""
    tf_s = interval_seconds(timeframe)
    decision = candle_ts + tf_s
    lag = now - decision
    if lag < 0:
        return SignalResult([], ["candle not closed yet"])
    if lag > (max_lag_s if max_lag_s is not None else tf_s):
        return SignalResult([], [f"stale candle ({lag:.0f}s after close): no retroactive signals"])

    versions = (await db.scalars(select(ModelVersion).where(
        ModelVersion.listing_id == listing_id, ModelVersion.timeframe == timeframe, ModelVersion.active))).all()
    if not versions:
        return SignalResult([], [])
    base = await load_series(db, listing_id, timeframe, INFERENCE_LOOKBACK, until=ts_to_dt(candle_ts))
    if base.empty or int(base["time"].iloc[-1]) != candle_ts:
        return SignalResult([], ["signal candle not stored"])

    created: list[int] = []
    skipped: list[str] = []
    htf_cache: dict[str, Any] = {}
    for mv in versions:
        htf = mv.htf_timeframe
        if htf and htf in stale_htf:
            skipped.append(f"{mv.key}: {htf} data stale")
            continue
        if htf and htf not in htf_cache:
            # only higher-TF candles that had closed by the decision time
            htf_cache[htf] = await load_series(db, listing_id, htf, INFERENCE_HTF_LOOKBACK,
                                               until=ts_to_dt(decision - interval_seconds(htf)))
        try:
            row = latest_feature_row(base, timeframe, htf_cache.get(htf) if htf else None, htf, now=decision)
            sig = predictors.get(mv).predict_row(row)
        except (InsufficientData, ValueError, ModelDriftError, FileNotFoundError) as exc:
            skipped.append(f"{mv.key}: {exc}")
            log.warning("signal_skipped", key=mv.key, reason=str(exc))
            continue
        stmt = pg_insert(Signal).values(
            model_version_id=mv.id, listing_id=listing_id, instrument_id=instrument_id, timeframe=timeframe,
            horizon=mv.horizon, candle_ts=ts_to_dt(candle_ts), decision_at=ts_to_dt(decision),
            created_at=datetime.fromtimestamp(now, tz=UTC), direction="up" if sig.direction == "Up" else "down",
            p_up_raw=sig.p_up_raw, p_up=sig.p_up, confidence=sig.confidence, strength=sig.strength,
            model_usable=sig.model_usable, features=_jsonable(sig.features),
        ).on_conflict_do_nothing().returning(Signal.id)
        new_id = await db.scalar(stmt)
        if new_id is not None:
            created.append(new_id)
    return SignalResult(created, skipped)


def max_lag_default(timeframe: str) -> timedelta:
    return timedelta(seconds=interval_seconds(timeframe))

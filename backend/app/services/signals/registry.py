"""Register trained artifacts as model versions, and load predictors for live use.

``register_artifacts`` reads ``ml/artifacts/<key>/metadata.json``, maps each to its DB listing, records a
``model_versions`` row, activates it (one active model per listing/timeframe/horizon) when the feed can serve
it live, and adds the ingestion targets it needs (its timeframe and the higher timeframe).
``PredictorCache`` refuses to serve an artifact whose ``trained_at`` differs from the registered version, so a
retrain can never silently change live behaviour.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.market import InstrumentListing, Venue
from app.models.signals import IngestionTarget, ModelVersion
from ml.data.candles import interval_seconds, is_forex
from ml.inference.predictor import Predictor
from ml.training.model import load_artifact

log = get_logger(__name__)


class ModelDriftError(RuntimeError):
    """The artifact on disk is not the version that was registered."""


@dataclass(frozen=True)
class Registration:
    key: str
    status: str  # registered_active | registered_inactive | already_registered | skipped
    detail: str = ""


def _venue_of(meta: dict[str, Any]) -> str:
    # Artifacts from before metadata recorded the venue: forex/gold came from Twelve Data, crypto from USD-M futures.
    return str(meta.get("venue") or ("twelvedata" if is_forex(meta["symbol"]) else "binance_usdm"))


async def _ensure_target(db: AsyncSession, listing_id: int, timeframe: str, reason: str, priority: int) -> None:
    await db.execute(pg_insert(IngestionTarget).values(
        listing_id=listing_id, timeframe=timeframe, reason=reason, priority=priority).on_conflict_do_nothing())


async def register_artifacts(db: AsyncSession, settings: Settings, root: Path | None = None) -> list[Registration]:
    root = root or settings.artifacts_dir
    results: list[Registration] = []
    for meta_path in sorted(root.glob("*/metadata.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        results.append(await _register_one(db, settings, meta))
    await db.commit()
    return results


async def _register_one(db: AsyncSession, settings: Settings, meta: dict[str, Any]) -> Registration:
    key, venue, tf, horizon = meta["key"], _venue_of(meta), meta["interval"], int(meta["horizon"])
    listing = await db.scalar(select(InstrumentListing).join(Venue).where(
        Venue.code == venue, InstrumentListing.venue_symbol == meta["symbol"]))
    if listing is None:
        return Registration(key, "skipped", f"no listing for {venue}:{meta['symbol']}")
    trained_at = datetime.fromisoformat(meta["trained_at"])
    if await db.scalar(select(ModelVersion.id).where(ModelVersion.key == key, ModelVersion.trained_at == trained_at)):
        return Registration(key, "already_registered")

    live_ok, why = True, ""
    if venue == "twelvedata":
        has_target = await db.scalar(select(IngestionTarget.id).where(
            IngestionTarget.listing_id == listing.id, IngestionTarget.timeframe == tf, IngestionTarget.enabled))
        if interval_seconds(tf) < settings.twelve_data_min_live_tf_s:
            live_ok, why = False, f"Twelve Data plan cannot ingest {tf} live"
        elif not has_target:
            live_ok, why = False, f"no enabled {tf} ingestion target (Twelve Data request budget); enable one first"

    usability = meta.get("usability", {"usable": False, "reasons": ["no usability assessment"]})
    mv = ModelVersion(
        key=key, listing_id=listing.id, timeframe=tf, horizon=horizon, htf_timeframe=meta.get("htf_interval"),
        label_mode=meta.get("label", {}).get("mode", "open_to_open"), trained_at=trained_at,
        git_commit=meta.get("git_commit"), walk_forward_run_id=meta.get("walk_forward_run_id"),
        usable=bool(usability.get("usable")), metrics=meta.get("metrics", {}), calibration=meta["calibration"],
        strength=meta["strength"], usability=usability, active=False, note=why or None,
    )
    if live_ok:
        await db.execute(update(ModelVersion).where(
            ModelVersion.listing_id == listing.id, ModelVersion.timeframe == tf, ModelVersion.horizon == horizon,
            ModelVersion.active).values(active=False))
        mv.active = True
        await _ensure_target(db, listing.id, tf, "model", 25)
        if mv.htf_timeframe:
            await _ensure_target(db, listing.id, mv.htf_timeframe, "htf", 26)
    db.add(mv)
    await db.flush()
    log.info("model_registered", key=key, active=mv.active, note=why)
    return Registration(key, "registered_active" if mv.active else "registered_inactive", why)


class PredictorCache:
    def __init__(self, artifacts_dir: Path) -> None:
        self.root = artifacts_dir
        self._cache: dict[int, Predictor] = {}

    def get(self, mv: ModelVersion) -> Predictor:
        if mv.id not in self._cache:
            model, meta = load_artifact(mv.key, self.root)
            if datetime.fromisoformat(meta["trained_at"]) != mv.trained_at:
                raise ModelDriftError(f"{mv.key}: artifact trained_at {meta['trained_at']} != registered "
                                      f"{mv.trained_at.isoformat()}; register the new version first")
            self._cache[mv.id] = Predictor(model, meta)
        return self._cache[mv.id]

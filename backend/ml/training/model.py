"""Model definition and artifact storage (XGBoost native JSON + metadata JSON; no pickle).

metadata.json mirrors the planned ``model_versions`` row (instrument, tf, horizon, trained_at,
metrics_json, calibration_json, artifact_path) so Phase 2 can import it into Postgres.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from xgboost import XGBClassifier

from ml.data.candles import safe_symbol
from ml.settings import get_settings

# Same hyperparameters as the original train.py (not tuned in Phase 0).
MODEL_PARAMS: dict[str, Any] = {
    "n_estimators": 200,
    "max_depth": 4,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "eval_metric": "logloss",
    "tree_method": "hist",
}


def make_model(seed: int = 42) -> XGBClassifier:
    return XGBClassifier(**MODEL_PARAMS, random_state=seed, n_jobs=-1)


def model_key(symbol: str, interval: str, horizon: int) -> str:
    return f"{safe_symbol(symbol)}_{interval}_h{horizon}"


def artifact_dir(key: str, root: Path | None = None) -> Path:
    return (root or get_settings().artifacts_dir) / key


def save_artifact(model: XGBClassifier, metadata: dict[str, Any], root: Path | None = None) -> Path:
    path = artifact_dir(metadata["key"], root)
    path.mkdir(parents=True, exist_ok=True)
    model.save_model(path / "model.json")
    metadata = {**metadata, "artifact_path": str(path / "model.json")}
    text = json.dumps(metadata, indent=2, sort_keys=True)
    (path / "metadata.json").write_text(text, encoding="utf-8", newline="\n")
    return path


def load_artifact(key: str, root: Path | None = None) -> tuple[XGBClassifier, dict[str, Any]]:
    path = artifact_dir(key, root)
    if not (path / "model.json").exists():
        raise FileNotFoundError(f"no trained model for {key} in {path.parent} (run python -m ml.training.pipeline)")
    model = XGBClassifier()
    model.load_model(path / "model.json")
    return model, json.loads((path / "metadata.json").read_text(encoding="utf-8"))


def git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5,
                             cwd=Path(__file__).parent)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None

"""Demo trading log: SQLite store of walk-forward OUT-OF-SAMPLE predictions (one row per predicted candle).

Interim store until Postgres signal tracking exists (Phase 2), then this module is removed.
The old version logged in-sample predictions (model scored on its own training data); those are gone.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from ml.settings import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    model_key TEXT NOT NULL,
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL,
    horizon INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    git_commit TEXT,
    config_json TEXT NOT NULL,
    data_json TEXT NOT NULL,
    cuts_json TEXT NOT NULL,
    calibration_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS oos_predictions (
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    time INTEGER NOT NULL,
    block INTEGER NOT NULL,
    label INTEGER NOT NULL,
    p_raw REAL NOT NULL,
    p_cal REAL,
    strength TEXT,
    majority_pred INTEGER NOT NULL,
    PRIMARY KEY (run_id, time)
);
CREATE INDEX IF NOT EXISTS ix_runs_model ON runs(model_key, created_at);
"""

PRED_COLUMNS = ["time", "block", "label", "p_raw", "p_cal", "strength", "majority_pred"]


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or get_settings().predictions_db
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def save_run(conn: sqlite3.Connection, run: dict[str, Any], predictions: pd.DataFrame) -> str:
    run_id = uuid.uuid4().hex
    created = datetime.now(UTC).isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (run_id, run["model_key"], run["symbol"], run["interval"], int(run["horizon"]), created,
         run.get("git_commit"), json.dumps(run["config"]), json.dumps(run["data"]), json.dumps(run["cuts"]),
         json.dumps(run["calibration"])),
    )
    rows = predictions[PRED_COLUMNS].astype(object).where(predictions[PRED_COLUMNS].notna(), None)
    conn.executemany("INSERT INTO oos_predictions VALUES (?,?,?,?,?,?,?,?)",
                     [(run_id, *r) for r in rows.itertuples(index=False, name=None)])
    conn.commit()
    return run_id


def latest_runs(conn: sqlite3.Connection) -> pd.DataFrame:
    """Most recent run per model_key."""
    return pd.read_sql_query(
        """SELECT r.* FROM runs r
           JOIN (SELECT model_key, MAX(created_at) AS c FROM runs GROUP BY model_key) m
             ON r.model_key = m.model_key AND r.created_at = m.c
           ORDER BY r.symbol, r.horizon, r.interval""", conn)


def load_predictions(conn: sqlite3.Connection, run_id: str) -> pd.DataFrame:
    return pd.read_sql_query("SELECT * FROM oos_predictions WHERE run_id = ? ORDER BY time", conn, params=(run_id,))

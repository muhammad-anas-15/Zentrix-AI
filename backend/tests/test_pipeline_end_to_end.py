"""Offline end to end: cached candles -> walk-forward -> artifact -> live predictor -> generated report."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ml.calibration.strength import TIER_ORDER
from ml.data import history
from ml.demo_trading_logger import accuracy_report, store
from ml.inference.predictor import Predictor
from ml.settings import get_settings
from ml.training import pipeline
from ml.training.walk_forward import WalkForwardConfig
from tests.conftest import make_candles, resample


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("DATA_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("PREDICTIONS_DB", str(tmp_path / "log.sqlite3"))
    monkeypatch.setenv("ML_REPORT_PATH", str(tmp_path / "ML_REPORT.md"))
    get_settings.cache_clear()
    base = make_candles(5000, "15m", seed=5, price=1900.0)
    history.write_cache(base, "XAU/USD", "15m")
    history.write_cache(resample(base, "1h"), "XAU/USD", "1h")
    yield base
    get_settings.cache_clear()


def test_pipeline_artifact_predictor_report(env: pd.DataFrame) -> None:
    base = env
    now = int(base["time"].iloc[-1]) + 900
    conn = store.connect()
    meta = pipeline.run_model({"symbol": "XAU/USD", "interval": "15m", "horizon": 1}, months=3,
                              cfg=WalkForwardConfig(n_blocks=4), offline=True, conn=conn, now=now)
    conn.close()

    s = get_settings()
    saved = json.loads((s.artifacts_dir / "XAU_USD_15m_h1" / "metadata.json").read_text())
    assert saved["walk_forward_run_id"] == meta["walk_forward_run_id"]
    assert saved["calibration"]["method"] == "platt" and set(saved["strength"]["cuts"]) <= set(TIER_ORDER)

    # Live inference from the saved artifact on the last closed candle (a forming candle is appended).
    pred = Predictor.load("XAU/USD", "15m", 1)
    forming = pd.DataFrame([{"time": now, "open": 1.0, "high": 9e9, "low": 0.5, "close": 5.0, "volume": 1.0}])
    from ml.inference.features import latest_feature_row

    row = latest_feature_row(pd.concat([base, forming], ignore_index=True), "15m", resample(base, "1h"), "1h",
                             now=now + 30)
    sig = pred.predict_row(row)
    assert sig.candle_time == int(base["time"].iloc[-1])
    assert 0 < sig.p_up < 1 and sig.confidence >= 0.5 and sig.strength in TIER_ORDER
    assert sig.track_record == saved["strength"]["tier_stats"][sig.strength]

    # The report is generated from the stored OOS predictions.
    out = accuracy_report.generate_report()
    text = out.read_text(encoding="utf-8")
    conn = store.connect()
    p = store.load_predictions(conn, meta["walk_forward_run_id"])
    conn.close()
    n_oos = int((p["block"] >= 2).sum())
    acc = float((((p["p_cal"] >= 0.5).astype(int)) == p["label"])[p["block"] >= 2].mean())
    assert "XAU/USD 15m, next candle" in text
    assert f"{n_oos:,}" in text and f"{acc * 100:.1f}%" in text
    assert "Not financial advice" in text
    assert np.isclose(meta["metrics"]["accuracy"]["rate"], acc)

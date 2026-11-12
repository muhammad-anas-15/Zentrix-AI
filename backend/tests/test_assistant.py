"""The assistant output carries calibrated, artifact-derived numbers and a disclaimer; the prompt forbids
inventing accuracy figures."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from app.services.assistant import agent
from app.services.assistant.reasoning_prompt import build_prompt
from ml.calibration.strength import TIER_ORDER
from ml.data import history
from ml.demo_trading_logger import store
from ml.inference.features import latest_feature_row
from ml.settings import get_settings
from ml.training import pipeline
from ml.training.walk_forward import WalkForwardConfig
from tests.conftest import make_candles, resample


@pytest.fixture
def trained(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("DATA_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("PREDICTIONS_DB", str(tmp_path / "log.sqlite3"))
    get_settings.cache_clear()
    base = make_candles(4000, "15m", seed=8)
    htf = resample(base, "1h")
    history.write_cache(base, "EUR/USD", "15m")
    history.write_cache(htf, "EUR/USD", "1h")
    now = int(base["time"].iloc[-1]) + 900
    conn = store.connect()
    meta = pipeline.run_model({"symbol": "EUR/USD", "interval": "15m", "horizon": 1}, months=2,
                              cfg=WalkForwardConfig(n_blocks=4), offline=True, conn=conn, now=now)
    conn.close()
    row = latest_feature_row(base, "15m", htf, "1h", now=now)
    monkeypatch.setattr(agent, "live_feature_row", lambda symbol, interval: row)
    yield meta, row
    get_settings.cache_clear()


def test_run_assistant_uses_calibrated_artifact(trained) -> None:  # type: ignore[no-untyped-def]
    meta, row = trained
    out = agent.run_assistant("EUR/USD", "15m", use_llm=False, use_knowledge=False, use_news=False)
    assert out["signal_strength"] in TIER_ORDER
    assert 50.0 <= out["ml_confidence"] <= 100.0
    assert out["strength_track_record"] == meta["strength"]["tier_stats"][out["signal_strength"]]
    assert out["candle_time"] == int(row["time"].iloc[0])
    assert out["trend_next_5_candles"] == "N/A"  # no h5 model trained here
    assert "Not financial advice" in out["disclaimer"]
    assert out["model"]["key"] == "EUR_USD_15m_h1"


def test_prompt_forbids_invented_accuracy() -> None:
    prompt = build_prompt(
        {"symbol": "EUR/USD", "current_price": 1.1, "pattern": "Doji", "rsi": 50, "ml_signal": "Up",
         "ml_confidence": 53.2, "signal_strength": "Weak",
         "strength_track_record": {"n": 400, "rate": 0.531}},
        [], {"risk_level": "low", "flagged_items": []})
    assert "53.1% correct over 400 past out-of-sample signals" in prompt
    assert "Do not state or imply any accuracy" in prompt
    assert "not enough out-of-sample signals" in build_prompt(
        {"strength_track_record": None}, [], {"risk_level": "low"})


def test_live_feature_row_is_shared_by_both_horizons(trained, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[str] = []
    meta, row = trained

    def once(symbol: str, interval: str) -> pd.DataFrame:
        calls.append(symbol)
        return row

    monkeypatch.setattr(agent, "live_feature_row", once)
    agent.run_assistant("EUR/USD", "15m", use_knowledge=False, use_news=False)
    assert calls == ["EUR/USD"]

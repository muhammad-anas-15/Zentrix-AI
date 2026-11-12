"""Walk-forward evaluation + production training for every model in ml/config/models.yaml, then the report.

Run (from backend/):
    python -m ml.training.pipeline                      # all models, fetch/extend data, write report
    python -m ml.training.pipeline --only EUR_USD_15m_h1 --offline
Each run stores its OOS predictions in the demo trading log and writes ml/artifacts/<key>/{model,metadata}.json.
"""

from __future__ import annotations

import argparse
import logging
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from ml.calibration.strength import MIN_TIER_N, TIER_LEVELS
from ml.data.candles import HIGHER_TF
from ml.demo_trading_logger import store
from ml.demo_trading_logger.accuracy_report import generate_report
from ml.evaluation.metrics import summarize
from ml.features.builder import INFERENCE_HTF_LOOKBACK, INFERENCE_LOOKBACK, WARMUP, feature_columns
from ml.training.dataset import LabelEntry, load_dataset
from ml.training.model import MODEL_PARAMS, git_commit, model_key, save_artifact
from ml.training.walk_forward import WalkForwardConfig, fit_final_model, run_walk_forward

log = logging.getLogger("ml.pipeline")
CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "models.yaml"


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def run_model(spec: dict[str, Any], months: float, cfg: WalkForwardConfig, offline: bool,
              conn: Any, artifacts_root: Path | None = None, now: float | None = None,
              label_entry: LabelEntry = "next_open") -> dict[str, Any]:
    symbol, interval, horizon = spec["symbol"], spec["interval"], int(spec["horizon"])
    key = model_key(symbol, interval, horizon)
    ds, info = load_dataset(symbol, interval, horizon, months, offline=offline, now=now, entry=label_entry)
    log.info("%s: %d rows, walk-forward...", key, len(ds))
    result = run_walk_forward(ds, cfg)
    metrics = summarize(result.predictions)
    commit = git_commit()
    data = {**asdict(info), "flat_rate": info.flat_rate, "months": months}
    run_id = store.save_run(conn, {
        "model_key": key, "symbol": symbol, "interval": interval, "horizon": horizon, "git_commit": commit,
        "config": cfg.to_dict(), "data": data, "cuts": result.cuts, "calibration": result.calibrator.to_dict(),
    }, result.predictions)

    model = fit_final_model(ds, cfg.seed)
    metadata = {
        "key": key, "symbol": symbol, "interval": interval, "horizon": horizon,
        "htf_interval": HIGHER_TF.get(interval),
        "label": {"entry": label_entry, "exit": f"close of candle t+{horizon}",
                  "up": "exit > entry", "flat": "excluded"},
        "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_commit": commit, "walk_forward_run_id": run_id,
        "feature_cols": feature_columns(), "model_params": MODEL_PARAMS,
        "pipeline": {"warmup": WARMUP, "inference_lookback": INFERENCE_LOOKBACK,
                     "inference_htf_lookback": INFERENCE_HTF_LOOKBACK},
        "data": data, "walk_forward": cfg.to_dict(),
        "metrics": {k: metrics[k] for k in ("n_oos", "period", "accuracy", "baseline_accuracy", "up_rate",
                                            "brier", "log_loss", "ece_raw", "ece_cal")},
        "calibration": result.calibrator.to_dict(),
        "strength": {"cuts": result.cuts, "levels": dict(TIER_LEVELS), "min_n": cfg.min_tier_n,
                     "tier_stats": metrics["tiers"]},
    }
    path = save_artifact(model, metadata, artifacts_root)
    acc = metrics["accuracy"]
    log.info("%s: OOS accuracy %.3f (n=%d) vs baseline %.3f; tiers %s -> %s", key, acc["rate"], acc["n"],
             metrics["baseline_accuracy"]["rate"], {t: c for t, c in result.cuts.items() if c}, path)
    return metadata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--only", nargs="*", help="model keys, e.g. EUR_USD_15m_h1")
    parser.add_argument("--offline", action="store_true", help="use cached/imported candles only")
    parser.add_argument("--no-report", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    config = load_config(args.config)
    cfg = WalkForwardConfig(**config.get("walk_forward", {}))
    if cfg.min_tier_n < MIN_TIER_N:
        log.warning("min_tier_n=%d is below the default %d", cfg.min_tier_n, MIN_TIER_N)
    specs = [s for s in config["models"]
             if not args.only or model_key(s["symbol"], s["interval"], int(s["horizon"])) in args.only]
    failures: list[str] = []
    conn = store.connect()
    try:
        for spec in specs:
            key = model_key(spec["symbol"], spec["interval"], int(spec["horizon"]))
            start = time.monotonic()
            try:
                run_model(spec, config["history_months"][spec["interval"]], cfg, args.offline, conn,
                          label_entry=config.get("label_entry", "next_open"))
            except Exception as exc:  # keep going; report what failed
                log.exception("%s failed: %s", key, exc)
                failures.append(f"{key}: {exc}")
            log.info("%s done in %.0fs", key, time.monotonic() - start)
    finally:
        conn.close()
    if not args.no_report:
        log.info("Report written to %s", generate_report())
    for f in failures:
        log.error("FAILED %s", f)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

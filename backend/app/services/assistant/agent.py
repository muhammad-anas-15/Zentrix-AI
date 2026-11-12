"""Assistant orchestrator: calibrated ML signal + knowledge base + news risk -> explainable result.

All model numbers come from the trained artifact (calibrated probability, earned strength tier and that
tier's measured out-of-sample track record). Signals are computed on the last CLOSED candle.
Not financial advice.
"""

from __future__ import annotations

import logging
from typing import Any

from app.services.assistant.reasoning_prompt import build_prompt
from ml.inference.predictor import Predictor, Signal, live_feature_row

log = logging.getLogger(__name__)
DISCLAIMER = "Not financial advice. Signals are probabilities based on past data, not guarantees."


def _trend_5(symbol: str, interval: str, row: Any) -> Signal | None:
    try:
        return Predictor.load(symbol, interval, horizon=5).predict_row(row)
    except FileNotFoundError:
        return None


def _knowledge(features: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        from knowledge.retriever import build_query_from_features, retrieve_knowledge
    except ImportError:  # optional extra: pip install -e ".[knowledge]"
        return []
    try:
        return retrieve_knowledge(build_query_from_features(features), top_k=3,
                                  pattern_name=features["pattern"], rsi=features["rsi"])
    except Exception:
        log.exception("knowledge retrieval failed")
        return []


def _news() -> dict[str, Any]:
    try:
        from app.services.news.keyword_flags import check_news_risk

        return check_news_risk()
    except Exception:
        log.exception("news check failed")
        return {"risk_level": "unknown", "flagged_items": []}


def run_assistant(symbol: str = "EUR/USD", interval: str = "15m", use_llm: bool = False,
                  use_knowledge: bool = True, use_news: bool = True) -> dict[str, Any]:
    row = live_feature_row(symbol, interval)
    signal = Predictor.load(symbol, interval, horizon=1).predict_row(row)
    trend = _trend_5(symbol, interval, row)
    f = signal.features

    knowledge = _knowledge(f) if use_knowledge else []
    news = _news() if use_news else {"risk_level": "unknown", "flagged_items": []}

    result: dict[str, Any] = {
        "symbol": symbol,
        "interval": interval,
        "candle_time": signal.candle_time,
        "price": f["current_price"],
        "pattern": f["pattern"],
        "rsi": f["rsi"],
        "ml_signal": signal.direction,
        "ml_confidence": round(signal.confidence * 100, 1),
        "signal_strength": signal.strength,
        "strength_track_record": signal.track_record,
        "trend_next_5_candles": trend.direction if trend else "N/A",
        "trend_next_5_confidence": round(trend.confidence * 100, 1) if trend else None,
        "trend_next_5_strength": trend.strength if trend else None,
        "possible_target_up": f["resistance"],
        "possible_target_down": f["support"],
        "knowledge_matches": [k["title"] for k in knowledge],
        "news_risk_level": news["risk_level"],
        "model": {"key": signal.model_key, "trained_at": signal.model_trained_at},
        "disclaimer": DISCLAIMER,
    }
    if use_llm:
        from app.services.assistant.llm_client import generate_explanation

        result["explanation"] = generate_explanation(build_prompt({**f, **result, "symbol": symbol}, knowledge, news))
    else:
        result["explanation"] = None
    return result

"""
Main orchestrator: coordinates all previous phases into one final,
explainable insight. This is what the backend API (Phase 5+) will call.

Flow:
  live candles -> features (Phase 1)
             -> ML prediction (Phase 2)
             -> RAG knowledge (Phase 3)
             -> news risk check (Phase 4)
             -> grounded LLM explanation (Phase 4)
             -> final combined result
"""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pickle
import pandas as pd

from data_pipeline.fetch_binance import fetch_binance_ohlcv
from data_pipeline.fetch_forex import fetch_forex_ohlcv
from features.feature_builder import build_features
from knowledge_base.retriever import retrieve_knowledge, build_query_from_features
from features.multi_timeframe import get_current_higher_tf_trend
from news_layer.keyword_flags import check_news_risk
from orchestrator.reasoning_prompt import build_prompt
from orchestrator.llm_client import generate_explanation

MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "ml_model", "model_registry")


def is_forex_symbol(symbol: str) -> bool:
    """Forex pairs contain '/' e.g. 'EUR/USD'. Crypto pairs don't e.g. 'BTCUSDT'."""
    return "/" in symbol


def fetch_candles(symbol: str, interval: str, limit: int = 100):
    """Routes to Binance (crypto) or Twelve Data (forex) automatically."""
    if is_forex_symbol(symbol):
        forex_interval = {"15m": "15min", "1h": "1h", "5m": "5min", "1m": "1min"}.get(interval, interval)
        return fetch_forex_ohlcv(symbol, forex_interval, outputsize=limit)
    return fetch_binance_ohlcv(symbol, interval, limit=limit)


def confidence_label(confidence: float) -> str:
    if confidence >= 70:
        return "Strong"
    elif confidence >= 65:
        return "Good"
    elif confidence >= 60:
        return "Moderate"
    elif confidence >= 55:
        return "Weak"
    return "Very Weak - Wait"


def load_ml_model(symbol: str, interval: str, horizon: int = 1):
    safe_symbol = symbol.replace("/", "_")
    suffix = f"_h{horizon}" if horizon > 1 else ""
    path = os.path.join(MODEL_DIR, f"{safe_symbol}_{interval}{suffix}_xgb.pkl")
    if not os.path.exists(path):
        return None, None
    with open(path, "rb") as f:
        payload = pickle.load(f)
    return payload["model"], payload["feature_cols"]


def get_ml_signal(features: dict, model, feature_cols) -> dict:
    """Returns {signal: 'Up'/'Down'/'N/A', confidence: float}"""
    if model is None:
        return {"signal": "N/A", "confidence": 0}

    row = {col: features.get(col, 0) for col in feature_cols
           if not col.startswith(("pattern_", "prev1_", "prev2_", "prev3_"))}
    for col in feature_cols:
        if col.startswith("pattern_"):
            row[col] = 1 if col == f"pattern_{features['pattern']}" else 0
        elif col.startswith("prev1_"):
            row[col] = 1 if col == f"prev1_{features['prev_pattern_1']}" else 0
        elif col.startswith("prev2_"):
            row[col] = 1 if col == f"prev2_{features['prev_pattern_2']}" else 0
        elif col.startswith("prev3_"):
            row[col] = 1 if col == f"prev3_{features['prev_pattern_3']}" else 0

    X = pd.DataFrame([row])[feature_cols]
    proba = model.predict_proba(X)[0]
    pred = model.predict(X)[0]
    confidence = round(max(proba) * 100, 1)
    signal = "Up" if pred == 1 else "Down"
    return {"signal": signal, "confidence": confidence}


def run_assistant(symbol: str = "BTCUSDT", interval: str = "15m", use_llm: bool = True) -> dict:
    # 1. Fetch live data + build features (Phase 1)
    candles = fetch_candles(symbol, interval, limit=100)
    features = build_features(candles)

    features["higher_tf_bullish"] = get_current_higher_tf_trend(symbol, interval)

    history = features.get("candles_with_patterns", [])
    prev_patterns = [c["pattern"] for c in history[-4:-1]] if len(history) >= 4 else ["None", "None", "None"]
    while len(prev_patterns) < 3:
        prev_patterns.insert(0, "None")
    features["prev_pattern_1"], features["prev_pattern_2"], features["prev_pattern_3"] = prev_patterns

    # 2. ML prediction (Phase 2)
    model, feature_cols = load_ml_model(symbol, interval)
    ml_result = get_ml_signal(features, model, feature_cols) if model else {"signal": "N/A", "confidence": 0}

    # Optional: 5-candle-ahead trend (Option B) — only if a horizon=5 model exists
    model_5, feature_cols_5 = load_ml_model(symbol, interval, horizon=5)
    trend_5_result = get_ml_signal(features, model_5, feature_cols_5) if model_5 else {"signal": "N/A", "confidence": 0}

    # 3. RAG knowledge retrieval (Phase 3)
    query = build_query_from_features(features)
    knowledge = retrieve_knowledge(query, top_k=3, pattern_name=features["pattern"], rsi=features["rsi"])

    # 4. News/risk check (Phase 4)
    news = check_news_risk()

    # 5. Build grounded prompt + explanation
    market_data = {**features, "symbol": symbol,
                   "ml_signal": ml_result["signal"], "ml_confidence": ml_result["confidence"]}
    prompt = build_prompt(market_data, knowledge, news)

    explanation = generate_explanation(prompt) if use_llm else "(LLM explanation skipped)"

    return {
        "symbol": symbol,
        "price": features["current_price"],
        "pattern": features["pattern"],
        "rsi": features["rsi"],
        "ml_signal": ml_result["signal"],
        "ml_confidence": ml_result["confidence"],
        "signal_strength": confidence_label(ml_result["confidence"]),
        "trend_next_5_candles": trend_5_result["signal"],
        "trend_next_5_confidence": trend_5_result["confidence"],
        "possible_target_up": features.get("resistance"),
        "possible_target_down": features.get("support"),
        "knowledge_matches": [k["title"] for k in knowledge],
        "news_risk_level": news["risk_level"],
        "explanation": explanation,
    }


if __name__ == "__main__":
    result = run_assistant("BTCUSDT", "15m", use_llm=False)  # set True once GEMINI_API_KEY is set
    for k, v in result.items():
        print(f"{k}: {v}")
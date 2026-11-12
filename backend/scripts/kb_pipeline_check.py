"""
Full pipeline test: live candles -> Phase 1 features -> Phase 3 RAG retrieval.
No GUI needed — console output shows exactly what a real signal would produce.
Run (from backend/): python -m scripts.kb_pipeline_check
"""
import sys, os

from ml.data.sources.binance import fetch_binance_ohlcv
from ml.features.builder import build_features
from knowledge.retriever import retrieve_knowledge, build_query_from_features

candles = fetch_binance_ohlcv("BTCUSDT", "15m", limit=100)
features = build_features(candles)

print("=== LIVE MARKET SNAPSHOT ===")
print(f"Price: {features['current_price']}")
print(f"Pattern detected: {features['pattern']}")
print(f"RSI: {features['rsi']}")
print(f"MACD hist (norm): {features['macd_hist_norm']}")

query = build_query_from_features(features)
print(f"\nGenerated RAG query: {query}")

print("\n=== RETRIEVED KNOWLEDGE ===")
for r in retrieve_knowledge(query, top_k=3, pattern_name=features['pattern'], rsi=features['rsi']):
    print(f"[{r['relevance_score']}] {r['title']}")
    print(f"  {r['content'][:150]}...\n")
"""Manual check: run a handful of realistic queries against the knowledge base and eyeball the results.

Run (from backend/):  python -m knowledge.ingest && python -m scripts.kb_retrieval_check
"""

from __future__ import annotations

from knowledge.retriever import retrieve_knowledge

QUERIES = [
    "Doji candlestick indecision pattern",
    "Bullish Engulfing near support, RSI oversold",
    "Shooting Star after uptrend near resistance",
    "MACD bearish momentum, price below EMA50",
    "Head and Shoulders reversal pattern",
    "high volatility news event risk",
]

if __name__ == "__main__":
    for q in QUERIES:
        print(f"\nQuery: {q}")
        for r in retrieve_knowledge(q, top_k=2):
            print(f"  [{r['relevance_score']}] {r['title']}")

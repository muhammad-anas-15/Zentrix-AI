"""
Manual test — run a handful of realistic queries and eyeball the results.
python knowledge_base/test_retrieval.py
"""
import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from retriever import retrieve_knowledge

test_queries = [
    "Doji candlestick indecision pattern",
    "Bullish Engulfing near support, RSI oversold",
    "Shooting Star after uptrend near resistance",
    "MACD bearish momentum, price below EMA50",
    "Head and Shoulders reversal pattern",
    "high volatility news event risk",
]

for q in test_queries:
    print(f"\nQuery: {q}")
    for r in retrieve_knowledge(q, top_k=2):
        print(f"  [{r['relevance_score']}] {r['title']}")
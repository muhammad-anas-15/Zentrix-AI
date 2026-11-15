"""Manual check: live closed-candle features -> knowledge retrieval. Needs network and the knowledge extra.

Run (from backend/):  python -m knowledge.ingest && python -m scripts.kb_pipeline_check [SYMBOL] [INTERVAL]
"""

from __future__ import annotations

import sys

from knowledge.retriever import build_query_from_features, retrieve_knowledge
from ml.inference.predictor import live_feature_row


def main() -> None:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    interval = sys.argv[2] if len(sys.argv) > 2 else "15m"
    f = live_feature_row(symbol, interval).iloc[0].to_dict()
    print(f"{symbol} {interval}: price {f['current_price']}, pattern {f['pattern']}, RSI {f['rsi']:.1f}")
    query = build_query_from_features(f)
    print("Query:", query)
    for r in retrieve_knowledge(query, top_k=3, pattern_name=f["pattern"], rsi=f["rsi"]):
        print(f"[{r['relevance_score']}] {r['title']}: {r['content'][:120]}...")


if __name__ == "__main__":
    main()

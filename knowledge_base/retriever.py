"""
Retrieves relevant knowledge base entries given the CURRENT live market
context (pattern + indicators from Phase 1's feature_builder.py).
This is what the orchestrator (Phase 4) will call to ground its
reasoning in real trading knowledge instead of guessing.
"""
import os
import chromadb
from chromadb.utils import embedding_functions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VECTOR_STORE_DIR = os.path.join(BASE_DIR, "vector_store")
COLLECTION_NAME = "trading_knowledge"
EMBED_MODEL = "all-MiniLM-L6-v2"

_client = None
_collection = None


def _get_collection():
    """Lazy-load the Chroma collection (avoids reloading model on every call)."""
    global _client, _collection
    if _collection is None:
        _client = chromadb.PersistentClient(path=VECTOR_STORE_DIR)
        embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=EMBED_MODEL
        )
        _collection = _client.get_collection(COLLECTION_NAME, embedding_function=embed_fn)
    return _collection


def retrieve_knowledge(query: str, top_k: int = 4, pattern_name: str = None,
                        rsi: float = None) -> list:
    """
    query: free-text description of current market situation
    pattern_name: exact pattern title for guaranteed top match
    rsi: if provided and extreme (>70 or <30), RSI entry is force-included
    Returns list of {title, content, category, relevance_score}
    """
    collection = _get_collection()
    matches = []
    seen_titles = set()

    def add_exact(title, score=1.0):
        if title in seen_titles:
            return
        exact = collection.get(where={"title": title})
        if exact["ids"]:
            matches.append({
                "title": exact["metadatas"][0]["title"],
                "category": exact["metadatas"][0]["category"],
                "content": exact["documents"][0],
                "relevance_score": score,
            })
            seen_titles.add(title)

    if pattern_name:
        add_exact(pattern_name, 1.0)

    if rsi is not None and (rsi > 70 or rsi < 30):
        add_exact("RSI (Relative Strength Index)", 0.95)

    # When a clear-direction pattern is detected, hide the OPPOSITE-direction
    # generic entries so results stay focused and don't confuse the user.
    NOISE_PAIRS = {
        "Bullish Candle": ["Bearish Candle", "Bearish Harami", "Bearish Engulfing"],
        "Bearish Candle": ["Bullish Candle", "Bullish Harami", "Bullish Engulfing"],
        "Bullish Engulfing": ["Bearish Engulfing", "Bearish Harami", "Bearish Candle"],
        "Bearish Engulfing": ["Bullish Engulfing", "Bullish Harami", "Bullish Candle"],
        "Hammer": ["Shooting Star", "Hanging Man"],
        "Shooting Star": ["Hammer", "Inverted Hammer"],
        "Doji": ["Bullish Harami", "Bearish Harami", "Bullish Engulfing", "Bearish Engulfing"],
    }
    skip_titles = set(NOISE_PAIRS.get(pattern_name, []))

    results = collection.query(query_texts=[query], n_results=top_k + 2)
    for i in range(len(results["ids"][0])):
        title = results["metadatas"][0][i]["title"]
        if title in seen_titles or title in skip_titles:
            continue
        matches.append({
            "title": title,
            "category": results["metadatas"][0][i]["category"],
            "content": results["documents"][0][i],
            "relevance_score": round(1 - results["distances"][0][i], 4),
        })
        seen_titles.add(title)
        if len(matches) >= top_k:
            break

    return matches[:top_k]


def build_query_from_features(features: dict) -> str:
    """
    Converts Phase 1's feature_builder.py output into a natural-language
    query string for retrieval. Combines pattern + key indicator states.
    """
    parts = [f"{features['pattern']} candlestick pattern {features['pattern']}"]  # repeated for retrieval weight

    if features["rsi"] > 70:
        parts.append("RSI overbought")
    elif features["rsi"] < 30:
        parts.append("RSI oversold")

    if features["macd_hist_norm"] > 0:
        parts.append("MACD bullish momentum")
    else:
        parts.append("MACD bearish momentum")

    if abs(features["price_vs_support_pct"]) < 0.5:
        parts.append("price near support level")
    if abs(features["price_vs_resistance_pct"]) < 0.5:
        parts.append("price near resistance level")

    return ", ".join(parts)


if __name__ == "__main__":
    # quick manual test — run after ingest.py has been run at least once
    sample_query = "Bullish Engulfing candlestick pattern near support, RSI oversold"
    results = retrieve_knowledge(sample_query, top_k=3)
    for r in results:
        print(f"[{r['relevance_score']}] {r['title']}: {r['content'][:100]}...")
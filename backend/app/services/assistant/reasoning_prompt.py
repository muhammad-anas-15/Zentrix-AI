"""
Prompt template for the final reasoning step. Explicitly instructs the
LLM to use ONLY the provided data — no outside knowledge, no invented
facts. This is what keeps the assistant explainable and honest.
"""

REASONING_PROMPT_TEMPLATE = """You are a trading assistant that explains market
conditions in simple, plain language for a non-technical user. You must
follow these rules strictly:

1. Use ONLY the information provided below — do not add outside facts,
   do not guess prices, do not invent news or events not listed here.
2. Never claim certainty about future price direction. Use words like
   "may", "often", "historically tends to" — not "will".
3. Keep the explanation short (3-5 sentences), simple, non-technical.
4. Always end by reminding the user this is not a guarantee and they
   should make their own final decision.
5. Do not state or imply any accuracy, win rate or profit figure other than
   the measured track record given below, and never promise profit.

=== LIVE MARKET DATA ===
Symbol: {symbol}
Current Price: {price}
Detected Pattern: {pattern}
RSI: {rsi}
MACD momentum: {macd_direction}
Price vs Support: {price_vs_support_pct}%
Price vs Resistance: {price_vs_resistance_pct}%
ML Model Signal: {ml_signal} (calibrated probability: {ml_confidence}%, strength: {strength})
Measured out-of-sample track record of this strength level: {track_record}

=== RELEVANT BOOK/STRATEGY KNOWLEDGE ===
{knowledge_context}

=== NEWS/RISK CONTEXT ===
Risk level today: {news_risk_level}
{news_flags}

Now write the plain-language explanation following the rules above."""


def build_prompt(market_data: dict, knowledge: list, news: dict) -> str:
    knowledge_text = "\n".join(
        f"- {k['title']}: {k['content']}" for k in knowledge
    ) or "No specific matching knowledge found."

    news_flags_text = "\n".join(
        f"- {item['title']}" for item in news.get("flagged_items", [])[:3]
    ) or "No major flagged events."

    return REASONING_PROMPT_TEMPLATE.format(
        symbol=market_data.get("symbol", "N/A"),
        price=market_data.get("current_price", "N/A"),
        pattern=market_data.get("pattern", "N/A"),
        rsi=market_data.get("rsi", "N/A"),
        macd_direction="bullish" if market_data.get("macd_hist_norm", 0) > 0 else "bearish",
        price_vs_support_pct=market_data.get("price_vs_support_pct", "N/A"),
        price_vs_resistance_pct=market_data.get("price_vs_resistance_pct", "N/A"),
        ml_signal=market_data.get("ml_signal", "N/A"),
        ml_confidence=market_data.get("ml_confidence", "N/A"),
        strength=market_data.get("signal_strength", "N/A"),
        track_record=_track_record_text(market_data.get("strength_track_record")),
        knowledge_context=knowledge_text,
        news_risk_level=news.get("risk_level", "unknown"),
        news_flags=news_flags_text,
    )

def _track_record_text(stats: dict | None) -> str:
    if not stats or not stats.get("n"):
        return "not enough out-of-sample signals to measure"
    return f"{stats['rate'] * 100:.1f}% correct over {stats['n']} past out-of-sample signals"

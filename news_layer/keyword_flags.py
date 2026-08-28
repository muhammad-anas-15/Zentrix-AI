"""
Rule-based flagging of risk-relevant news/events — no ML/LLM needed here,
just keyword matching. This adds honest "be careful today" context
without pretending to predict direction from news.
"""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from news_layer.rss_fetcher import fetch_headlines
from news_layer.economic_calendar import fetch_economic_events

RISK_KEYWORDS = [
    "war", "conflict", "invasion", "sanctions", "attack",
    "rate hike", "rate cut", "fed", "interest rate", "inflation",
    "recession", "crash", "sell-off", "selloff", "default",
    "shutdown", "election", "geopolitical",
]


def check_news_risk() -> dict:
    """
    Returns {risk_level: 'low'|'medium'|'high', flagged_items: [...]}
    """
    flagged = []

    headlines = fetch_headlines()
    for h in headlines:
        text = (h["title"] + " " + h.get("summary", "")).lower()
        matched = [kw for kw in RISK_KEYWORDS if kw in text]
        if matched:
            flagged.append({
                "type": "news", "title": h["title"],
                "matched_keywords": matched, "source": h["source"],
            })

    events = fetch_economic_events(min_impact="High")
    for e in events:
        flagged.append({
            "type": "economic_event", "title": e["title"],
            "country": e["country"], "date": e["date"],
        })

    if len(flagged) == 0:
        risk_level = "low"
    elif len(flagged) <= 2:
        risk_level = "medium"
    else:
        risk_level = "high"

    return {"risk_level": risk_level, "flagged_items": flagged}


if __name__ == "__main__":
    result = check_news_risk()
    print(f"Risk level: {result['risk_level']}")
    for item in result["flagged_items"][:5]:
        print(" -", item)
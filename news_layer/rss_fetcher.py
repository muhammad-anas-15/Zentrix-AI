"""
Fetches latest headlines from free, public RSS feeds (no API key needed).
Used only for keyword-based risk flagging — NOT for sentiment prediction.
"""
import feedparser

FREE_RSS_FEEDS = {
    "reuters_business": "https://feeds.reuters.com/reuters/businessNews",
    "investing_economy": "https://www.investing.com/rss/news_25.rss",
}


def fetch_headlines(max_items: int = 15) -> list:
    """
    Returns list of {title, summary, source, published} from all configured feeds.
    """
    headlines = []
    for source, url in FREE_RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:max_items]:
                headlines.append({
                    "title": entry.get("title", ""),
                    "summary": entry.get("summary", ""),
                    "source": source,
                    "published": entry.get("published", ""),
                })
        except Exception as e:
            print(f"Warning: failed to fetch {source}: {e}")
    return headlines


if __name__ == "__main__":
    for h in fetch_headlines()[:5]:
        print(f"[{h['source']}] {h['title']}")
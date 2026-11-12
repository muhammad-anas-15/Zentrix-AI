"""
Fetches this week's economic calendar events using ForexFactory's free
public JSON feed (widely used by open-source trading tools, no key needed).
"""
import requests

CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"


def fetch_economic_events(min_impact: str = "High") -> list:
    """
    min_impact: 'Low', 'Medium', 'High' — filters to only that impact or higher.
    Returns list of {title, country, date, impact, forecast, previous}
    """
    impact_rank = {"Low": 1, "Medium": 2, "High": 3}
    min_rank = impact_rank.get(min_impact, 3)

    try:
        resp = requests.get(CALENDAR_URL, timeout=10)
        resp.raise_for_status()
        events = resp.json()
    except Exception as e:
        print(f"Warning: failed to fetch economic calendar: {e}")
        return []

    filtered = []
    for e in events:
        impact = e.get("impact", "Low")
        if impact_rank.get(impact, 0) >= min_rank:
            filtered.append({
                "title": e.get("title", ""),
                "country": e.get("country", ""),
                "date": e.get("date", ""),
                "impact": impact,
                "forecast": e.get("forecast", ""),
                "previous": e.get("previous", ""),
            })
    return filtered


if __name__ == "__main__":
    events = fetch_economic_events("High")
    print(f"Found {len(events)} high-impact events this week")
    for e in events[:5]:
        print(f"{e['date']} [{e['country']}] {e['title']}")
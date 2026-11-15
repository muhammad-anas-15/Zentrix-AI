"""News guard rules and calendar parsing (no database)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.news.calendar import parse_calendar
from app.services.news.guard import GuardConfig, evaluate_guard, instrument_currencies

NOW = datetime(2026, 11, 11, 13, 0, tzinfo=UTC)
CFG = GuardConfig()


def ev(minutes: float, impact: str = "high", currency: str = "USD", title: str = "CPI m/m") -> object:
    class E:
        pass

    e = E()
    e.title, e.currency, e.impact = title, currency, impact  # type: ignore[attr-defined]
    e.event_at = NOW + timedelta(minutes=minutes)  # type: ignore[attr-defined]
    return e


def guard(events: list, asset: tuple[str, str, str] = ("fx", "EUR", "USD"), fresh: bool = True):  # type: ignore[no-untyped-def]
    cur, high_only = instrument_currencies(*asset)
    return evaluate_guard(events, cur, high_only, NOW, CFG, NOW - timedelta(minutes=10) if fresh else None)


def test_parse_calendar_converts_to_utc_and_normalises() -> None:
    rows = [{"title": "CPI m/m", "country": "USD", "date": "2026-11-12T08:30:00-05:00", "impact": "High",
             "forecast": "0.3%", "previous": ""},
            {"title": "Bank Holiday", "country": "All", "date": "2026-11-11T00:00:00-05:00", "impact": "Holiday"},
            {"title": "Bad", "country": "EUR", "date": "not a date", "impact": "High"},
            {"title": "Naive", "country": "EUR", "date": "2026-11-12T08:30:00", "impact": "High"}]
    out = parse_calendar(rows)
    assert len(out) == 2
    cpi = out[0]
    assert cpi.event_at == datetime(2026, 11, 12, 13, 30, tzinfo=UTC)
    assert (cpi.impact, cpi.currency, cpi.forecast, cpi.previous) == ("high", "USD", "0.3%", None)
    assert out[1].currency == "All" and out[1].impact == "holiday"
    assert parse_calendar(rows)[0].external_id == cpi.external_id  # stable id


def test_blackout_window_is_30_min_each_side() -> None:
    for minutes in (29, 0, -29):
        g = guard([ev(minutes)])
        assert g.state == "blackout", minutes
        assert g.blackout_until == NOW + timedelta(minutes=minutes + 30)
    assert guard([ev(31)]).state == "caution"  # high impact within 2 h
    assert guard([ev(-31)]).state == "clear"
    assert guard([ev(121)]).state == "clear"


def test_medium_impact_is_caution_only_close_to_the_event() -> None:
    assert guard([ev(10, "medium")]).state == "caution"
    assert guard([ev(20, "medium")]).state == "clear"
    assert guard([ev(5, "low")]).state == "clear"


def test_currency_mapping() -> None:
    assert guard([ev(5, currency="JPY")]).state == "clear"  # EUR/USD unaffected by JPY
    assert guard([ev(5, currency="EUR")]).state == "blackout"
    assert guard([ev(5, currency="All")]).state == "blackout"
    gold = ("metal", "XAU", "USD")
    assert guard([ev(5, currency="USD")], gold).state == "blackout"
    assert guard([ev(5, currency="EUR")], gold).state == "clear"
    crypto = ("crypto", "BTC", "USDT")
    assert guard([ev(5, currency="USD")], crypto).state == "blackout"
    assert guard([ev(5, "medium", currency="USD")], crypto).state == "clear"  # crypto: high impact only


def test_stale_calendar_is_unknown_never_clear() -> None:
    g = guard([], fresh=False)
    assert g.state == "unknown"
    assert any("unknown" in r for r in g.reasons)
    assert guard([ev(5)], fresh=False).state == "blackout"  # a known blackout still wins


def test_countdown_to_next_event() -> None:
    g = guard([ev(-60), ev(300, "medium", title="PMI"), ev(90)])
    assert g.next_event is not None and g.next_event["title"] == "CPI m/m"
    assert g.countdown_s == 90 * 60
    assert g.state == "caution"


def test_week_window_is_sunday_to_sunday_new_york() -> None:
    from app.services.news.calendar import week_window

    start, end = week_window(NOW)  # Wednesday 2026-11-11
    assert start == datetime(2026, 11, 8, 5, 0, tzinfo=UTC)  # Sunday 00:00 EST
    assert end == datetime(2026, 11, 15, 5, 0, tzinfo=UTC)
    assert week_window(start)[0] == start
    assert week_window(datetime(2026, 11, 8, 4, 59, tzinfo=UTC))[0] == datetime(2026, 11, 1, 4, 0, tzinfo=UTC)  # EDT

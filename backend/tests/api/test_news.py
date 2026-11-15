"""News guard against Postgres: calendar ingestion (upsert, reschedules), worker refresh, API endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import fakeredis
import httpx
from fastapi import FastAPI

from app.core.config import Settings
from app.services.news.calendar import CalendarEvent, HttpCalendarSource, parse_calendar
from app.services.signals.registry import PredictorCache
from app.workers.ingest import Worker
from tests.api.conftest import Clock, scalar

NOW = datetime(2026, 11, 11, 13, 0, tzinfo=UTC)


def row(title: str, minutes: float, impact: str = "High", country: str = "USD") -> dict:
    at = (NOW + timedelta(minutes=minutes)).astimezone(UTC).isoformat()
    return {"title": title, "country": country, "date": at, "impact": impact, "forecast": "", "previous": ""}


class FakeCalendar:
    def __init__(self, *batches: list[dict]) -> None:
        self.batches = [parse_calendar(b) for b in batches]
        self.calls = 0
        self.fail = False

    async def fetch(self) -> list[list[CalendarEvent]]:
        self.calls += 1
        if self.fail:
            raise httpx.ConnectError("down")
        return self.batches


def worker(app: FastAPI, settings: Settings, redis: fakeredis.FakeAsyncRedis, cal: FakeCalendar,
           clock: Clock) -> Worker:
    return Worker(app.state.sessionmaker, redis, {}, PredictorCache(settings.artifacts_dir), settings, clock=clock,
                  calendar=cal)


async def test_worker_refreshes_calendar_hourly_and_drops_rescheduled_events(
        app: FastAPI, settings: Settings, fake_redis: fakeredis.FakeAsyncRedis, clock: Clock) -> None:
    clock.t = NOW.timestamp()
    cal = FakeCalendar([row("CPI m/m", 20), row("Retail Sales", 240, "Medium"), row("PMI", 60, "Low", "EUR")])
    w = worker(app, settings, fake_redis, cal, clock)
    await w.tick(NOW.timestamp())
    assert await scalar(app, "SELECT count(*) FROM news_events") == 3
    await w.tick(NOW.timestamp() + 60)
    assert cal.calls == 1  # hourly, not every tick

    # rescheduled: CPI moves by an hour inside the same file window; the old time must disappear
    cal.batches = [parse_calendar([row("CPI m/m", 80), row("Retail Sales", 240, "Medium"),
                                   row("PMI", 60, "Low", "EUR")])]
    await w.tick(NOW.timestamp() + 3601)
    assert cal.calls == 2
    assert await scalar(app, "SELECT count(*) FROM news_events") == 3
    at = await scalar(app, "SELECT event_at FROM news_events WHERE title = 'CPI m/m'")
    assert at == NOW + timedelta(minutes=80)

    cal.fail = True
    report = await w.tick(NOW.timestamp() + 2 * 3601)
    assert report.errors == ["calendar: ConnectError"]
    assert await scalar(app, "SELECT count(*) FROM news_events") == 3  # kept on failure


async def test_http_source_skips_unpublished_next_week() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "nextweek" in request.url.path:
            return httpx.Response(404, text="<html>404</html>")
        return httpx.Response(200, json=[row("CPI m/m", 20)])

    src = HttpCalendarSource(["https://x/ff_calendar_thisweek.json", "https://x/ff_calendar_nextweek.json"],
                             transport=httpx.MockTransport(handler))
    batches = await src.fetch()
    assert [len(b) for b in batches] == [1]


async def test_guard_and_events_endpoints(app: FastAPI, client: httpx.AsyncClient, settings: Settings,
                                          fake_redis: fakeredis.FakeAsyncRedis, clock: Clock) -> None:
    clock.t = NOW.timestamp()
    r = await client.get("/v1/news/guard", params={"symbol": "EUR/USD"})
    assert r.status_code == 200
    assert r.json()["state"] == "unknown"  # no calendar yet: never "clear"

    cal = FakeCalendar([row("CPI m/m", 20), row("ECB Press Conference", 300, "High", "EUR"),
                        row("BoJ Outlook", 10, "High", "JPY"), row("ISM", 10, "Medium")])
    await worker(app, settings, fake_redis, cal, clock).tick(NOW.timestamp())

    g = (await client.get("/v1/news/guard", params={"symbol": "EUR/USD"})).json()
    assert g["state"] == "blackout"
    assert g["currencies"] == ["EUR", "USD"]
    assert g["blackout_until"].startswith("2026-11-11T13:50")
    assert g["next_event"]["title"] == "ISM" and g["countdown_s"] == 600
    assert "Not financial advice" in g["disclaimer"]

    btc = (await client.get("/v1/news/guard", params={"symbol": "BTC/USDT"})).json()
    assert btc["state"] == "blackout" and [e["title"] for e in btc["active_events"]] == ["CPI m/m"]

    clock.t = (NOW + timedelta(minutes=55)).timestamp()
    later = (await client.get("/v1/news/guard", params={"symbol": "EUR/USD"})).json()
    assert later["state"] == "clear" and later["next_event"]["title"] == "ECB Press Conference"

    clock.t = NOW.timestamp()
    ev = (await client.get("/v1/news/events", params={"currency": "USD,EUR", "impact": "high"})).json()
    assert [e["title"] for e in ev["items"]] == ["CPI m/m", "ECB Press Conference"]
    assert ev["items"][0]["in_s"] == 1200
    assert ev["calendar_updated_at"] is not None

    r = await client.get("/v1/news/guard", params={"symbol": "NOPE/USD"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "unknown_instrument"

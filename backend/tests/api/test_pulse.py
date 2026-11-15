"""Market Pulse against Postgres: worker refresh (tagging, relevance filter, feed health, pruning) and the feed API."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import fakeredis
import httpx
from fastapi import FastAPI

from app.core.config import Settings
from app.services.news.headlines import FEEDS_BY_CODE, Feed, FeedResult, Headline
from app.services.signals.registry import PredictorCache
from app.workers.ingest import Worker
from tests.api.conftest import Clock, scalar

NOW = datetime(2026, 11, 15, 12, tzinfo=UTC)


def h(key: str, title: str, minutes_ago: float) -> Headline:
    return Headline(key.ljust(40, "0"), title, f"https://example.com/{key}", NOW - timedelta(minutes=minutes_ago))


class FakeHeadlines:
    def __init__(self) -> None:
        self.calls = 0
        self.items: dict[str, list[Headline]] = {
            "fed": [h("fed1", "Federal Reserve issues FOMC statement", 30),
                    h("fed2", "Federal Reserve Board announces pricing for payment services", 300)],
            "coindesk": [h("cd1", "Bitcoin slides to 3-month low of $65,000", 5),
                         h("cd2", "Exchange halts withdrawals after $40M hack", 50),
                         h("old", "Last month's story", 60 * 24 * 10)],
            "sec": [h("sec1", "SEC Proposes Executive Compensation Disclosure Reforms", 20),
                    h("sec2", "SEC charges crypto lender with fraud", 40)],
            "fxstreet": [h("fx1", "EUR/USD price forecast: euro holds above 1.10", 10),
                         h("fx2", "UK retail sales fall more than expected", 15)],
        }

    async def fetch(self, feeds: Sequence[Feed]) -> list[FeedResult]:
        self.calls += 1
        out = []
        for f in feeds:
            if f.code == "ecb":
                out.append(FeedResult(f, error="ConnectTimeout"))
            elif f.code in self.items:
                out.append(FeedResult(f, list(self.items[f.code])))
            else:
                out.append(FeedResult(f, not_modified=True))
        return out


def worker(app: FastAPI, settings: Settings, redis: fakeredis.FakeAsyncRedis, src: FakeHeadlines,
           clock: Clock) -> Worker:
    return Worker(app.state.sessionmaker, redis, {}, PredictorCache(settings.artifacts_dir), settings, clock=clock,
                  headlines=src)


async def test_worker_stores_tagged_headlines_and_feed_health(app: FastAPI, settings: Settings,
                                                             fake_redis: fakeredis.FakeAsyncRedis,
                                                             clock: Clock) -> None:
    clock.t = NOW.timestamp()
    src = FakeHeadlines()
    w = worker(app, settings, fake_redis, src, clock)
    await w.tick(NOW.timestamp())
    # 10-day-old story dropped; SEC compensation release is not market-relevant
    assert await scalar(app, "SELECT count(*) FROM news_items") == 7
    assert await scalar(app, "SELECT count(*) FROM news_items WHERE external_id LIKE 'sec1%'") == 0
    assert await scalar(app, "SELECT impact FROM news_items WHERE external_id LIKE 'fed1%'") == "high"
    assert await scalar(app, "SELECT assets FROM news_items WHERE external_id LIKE 'cd1%'") == ["CRYPTO", "BTC"]
    assert await scalar(app, "SELECT last_error FROM news_feed_status WHERE code = 'ecb'") == "ConnectTimeout"
    assert await scalar(app, "SELECT items FROM news_feed_status WHERE code = 'coindesk'") == 2
    await w.tick(NOW.timestamp() + 30)
    assert src.calls == 1  # every news_headlines_refresh_s, not every tick

    # a corrected headline is re-tagged; the stored row is updated, not duplicated
    src.items["fed"][0] = h("fed1", "Fed holds rates steady", 30)
    clock.t = NOW.timestamp() + settings.news_headlines_refresh_s + 1
    await w.tick(clock.t)
    assert src.calls == 2
    assert await scalar(app, "SELECT title FROM news_items WHERE external_id LIKE 'fed1%'") == "Fed holds rates steady"
    assert await scalar(app, "SELECT count(*) FROM news_items") == 7


async def test_feed_filters_and_pages(app: FastAPI, settings: Settings, fake_redis: fakeredis.FakeAsyncRedis,
                                      client: httpx.AsyncClient, clock: Clock) -> None:
    clock.t = NOW.timestamp()
    await worker(app, settings, fake_redis, FakeHeadlines(), clock).tick(NOW.timestamp())

    body = (await client.get("/v1/news/feed")).json()
    titles = [i["title"] for i in body["items"]]
    assert titles[0] == "Bitcoin slides to 3-month low of $65,000"  # newest first
    first = body["items"][0]
    assert first["source_name"] == "CoinDesk" and first["impact"] == "medium" and first["age_s"] == 300
    assert first["kind"] == "headline" and "BTC" in first["assets"] and first["url"].startswith("https://")
    assert "type of news, not the size or direction" in body["method"] and "Social media" in body["coverage"]
    ecb = next(s for s in body["sources"] if s["code"] == "ecb")
    assert ecb["ok"] is False and ecb["last_error"] == "ConnectTimeout"
    assert body["updated_at"] is not None

    high = (await client.get("/v1/news/feed", params={"impact": "high"})).json()["items"]
    assert {i["impact"] for i in high} == {"high"} and len(high) == 3  # FOMC, hack, SEC charges
    btc = (await client.get("/v1/news/feed", params={"asset": "btc"})).json()["items"]
    assert [i["title"] for i in btc] == ["Bitcoin slides to 3-month low of $65,000"]
    eurusd = (await client.get("/v1/news/feed", params={"symbol": "EUR/USD"})).json()["items"]
    assert {"EUR/USD price forecast: euro holds above 1.10", "Federal Reserve issues FOMC statement"} <= {
        i["title"] for i in eurusd} and all({"EUR", "USD"} & set(i["assets"]) for i in eurusd)
    cb = (await client.get("/v1/news/feed", params={"kind": "central_bank"})).json()["items"]
    assert {i["source"] for i in cb} == {"fed"}
    q = (await client.get("/v1/news/feed", params={"q": "retail"})).json()["items"]
    assert [i["title"] for i in q] == ["UK retail sales fall more than expected"]

    page1 = (await client.get("/v1/news/feed", params={"limit": 3})).json()
    page2 = (await client.get("/v1/news/feed", params={"limit": 3, "before_id": page1["next_before_id"]})).json()
    assert len(page1["items"]) == 3 and page1["next_before_id"] is not None
    assert not {i["id"] for i in page1["items"]} & {i["id"] for i in page2["items"]}
    r = await client.get("/v1/news/feed", params={"symbol": "NOPE/XYZ"})
    assert r.status_code == 404


async def test_disabled_feeds_are_hidden_and_old_items_pruned(app: FastAPI, settings: Settings,
                                                              fake_redis: fakeredis.FakeAsyncRedis,
                                                              client: httpx.AsyncClient, clock: Clock) -> None:
    clock.t = NOW.timestamp()
    src = FakeHeadlines()
    await worker(app, settings, fake_redis, src, clock).tick(NOW.timestamp())
    original = settings.news_feeds
    settings.news_feeds = ["fed"]
    try:
        body = (await client.get("/v1/news/feed")).json()
        assert {i["source"] for i in body["items"]} == {"fed"} and [s["code"] for s in body["sources"]] == ["fed"]
    finally:
        settings.news_feeds = original
    later = NOW + timedelta(days=settings.news_items_keep_days, hours=1)
    clock.t = later.timestamp()
    src.items = {}
    await worker(app, settings, fake_redis, src, clock).tick(later.timestamp())
    assert await scalar(app, "SELECT count(*) FROM news_items") == 0
    assert FEEDS_BY_CODE["fed"].kind == "central_bank"

"""Market headlines (Market Pulse) from RSS/Atom feeds into ``news_items``.

Sources are official central-bank and regulator feeds plus a few publisher headline feeds. Only the headline,
link, source and time are stored and shown (never article text); each item links out to its publisher. Publisher
feeds are offered for personal reading: their terms must be confirmed (or a licensed news API used) before a
commercial launch (docs/DATA_SOURCES.md). Feeds are polled every ``news_headlines_refresh_s`` with conditional
requests (ETag / Last-Modified); one failing feed never blocks the others.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Protocol

import httpx
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.tools import NewsFeedStatus, NewsItem
from app.services.news.classify import tag

log = get_logger(__name__)
MAX_FEED_BYTES = 3 * 1024 * 1024
MAX_ITEMS_PER_FEED = 60
TITLE_MAX = 300
KINDS = ("central_bank", "regulator", "headline")


@dataclass(frozen=True)
class Feed:
    code: str
    name: str
    kind: str  # central_bank | regulator | headline
    url: str
    assets: tuple[str, ...] = ()  # badges every item of this source gets (e.g. the ECB: EUR)
    relevant_only: bool = False  # keep only items that name an asset or match an impact rule


FEEDS: tuple[Feed, ...] = (
    Feed("fed", "Federal Reserve", "central_bank", "https://www.federalreserve.gov/feeds/press_all.xml", ("USD",)),
    Feed("ecb", "European Central Bank", "central_bank", "https://www.ecb.europa.eu/rss/press.html", ("EUR",)),
    Feed("boe", "Bank of England", "central_bank", "https://www.bankofengland.co.uk/rss/news", ("GBP",)),
    Feed("boj", "Bank of Japan", "central_bank", "https://www.boj.or.jp/en/rss/whatsnew.xml", ("JPY",)),
    Feed("sec", "U.S. SEC", "regulator", "https://www.sec.gov/news/pressreleases.rss", relevant_only=True),
    Feed("fxstreet", "FXStreet", "headline", "https://www.fxstreet.com/rss/news"),
    Feed("investinglive", "investingLive", "headline", "https://investinglive.com/feed/"),
    Feed("coindesk", "CoinDesk", "headline", "https://www.coindesk.com/arc/outboundfeeds/rss/", ("CRYPTO",)),
    Feed("cointelegraph", "Cointelegraph", "headline", "https://cointelegraph.com/rss", ("CRYPTO",)),
)
FEEDS_BY_CODE = {f.code: f for f in FEEDS}


@dataclass(frozen=True)
class Headline:
    external_id: str
    title: str
    url: str
    published_at: datetime


@dataclass
class FeedResult:
    feed: Feed
    items: list[Headline] = field(default_factory=list)
    error: str | None = None
    not_modified: bool = False


_TAGS = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


def clean_title(raw: str | None) -> str:
    text = html.unescape(_TAGS.sub(" ", raw or ""))
    return _SPACE.sub(" ", text).strip()[:TITLE_MAX]


def _local(tag_name: str) -> str:
    return tag_name.rsplit("}", 1)[-1]


def _child(el: ET.Element, *names: str) -> ET.Element | None:
    for c in el:
        if _local(c.tag) in names:
            return c
    return None


def _text(el: ET.Element, *names: str) -> str | None:
    c = _child(el, *names)  # an Element without children is falsy: compare with None
    return c.text if c is not None else None


def _date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip()
    try:
        dt = parsedate_to_datetime(raw)  # RSS: RFC 822
    except (TypeError, ValueError, IndexError):
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))  # Atom / dc:date: ISO 8601
        except ValueError:
            return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).astimezone(UTC)


def parse_feed(body: bytes, now: datetime) -> list[Headline]:
    """RSS 2.0 or Atom -> headlines (newest first as published). Items without a title or an http(s) link are
    skipped; a missing or future date becomes ``now``."""
    root = ET.fromstring(body)  # expat: no external entities; entity-expansion limits since 2.4.1
    out: list[Headline] = []
    for el in root.iter():
        if _local(el.tag) not in ("item", "entry"):
            continue
        title = clean_title(_text(el, "title"))
        link_el = _child(el, "link")
        link = ((link_el.get("href") or link_el.text or "") if link_el is not None else "").strip()
        if not title or not link.startswith(("https://", "http://")):
            continue
        guid = _text(el, "guid", "id") or link
        published = _date(_text(el, "pubDate", "published", "updated", "date")) or now
        out.append(Headline(hashlib.sha1(guid.strip().encode()).hexdigest(), title, link[:1000],
                            min(published, now)))
        if len(out) >= MAX_ITEMS_PER_FEED:
            break
    return out


class HeadlineSource(Protocol):
    async def fetch(self, feeds: Sequence[Feed]) -> list[FeedResult]: ...


class HttpHeadlineSource:
    """Fetches feeds concurrently with conditional GETs (validators kept per URL for the process lifetime)."""

    def __init__(self, timeout_s: float = 12.0, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.timeout_s = timeout_s
        self.transport = transport
        self._validators: dict[str, dict[str, str]] = {}

    async def _one(self, client: httpx.AsyncClient, feed: Feed, now: datetime) -> FeedResult:
        try:
            r = await client.get(feed.url, headers=self._validators.get(feed.url, {}))
            if r.status_code == 304:
                return FeedResult(feed, not_modified=True)
            r.raise_for_status()
            if len(r.content) > MAX_FEED_BYTES:
                return FeedResult(feed, error="feed too large")
            items = parse_feed(r.content, now)
            self._validators[feed.url] = {k: v for k, v in (("If-None-Match", r.headers.get("etag")),
                                                            ("If-Modified-Since", r.headers.get("last-modified")))
                                          if v}
            return FeedResult(feed, items)
        except (httpx.HTTPError, ET.ParseError, ValueError) as exc:
            log.warning("headline_feed_failed", feed=feed.code, error=type(exc).__name__)
            return FeedResult(feed, error=type(exc).__name__)

    async def fetch(self, feeds: Sequence[Feed]) -> list[FeedResult]:
        now = datetime.now(UTC)
        async with httpx.AsyncClient(timeout=self.timeout_s, transport=self.transport, follow_redirects=True,
                                     headers={"User-Agent": "zentrix-news/1.0"}) as client:
            return list(await asyncio.gather(*(self._one(client, f, now) for f in feeds)))


def enabled_feeds(codes: Iterable[str]) -> list[Feed]:
    wanted = [c.strip().lower() for c in codes if c.strip()]
    return [f for f in FEEDS if f.code in wanted] if wanted else list(FEEDS)


async def store_headlines(db: AsyncSession, feed: Feed, items: Sequence[Headline], now: datetime,
                          keep_days: int) -> int:
    """Tag and upsert one feed's items (re-tagging existing ones, so rule changes apply). Returns rows kept."""
    cutoff = now - timedelta(days=keep_days)
    rows = []
    for h in items:
        if h.published_at < cutoff:
            continue
        t = tag(h.title, feed.assets)
        if feed.relevant_only and t.impact == "low" and not t.assets:
            continue
        rows.append({"source": feed.code, "external_id": h.external_id, "title": h.title, "url": h.url,
                     "kind": feed.kind, "published_at": h.published_at, "impact": t.impact, "impact_reason": t.reason,
                     "assets": list(t.assets)})
    if rows:
        stmt = pg_insert(NewsItem).values(rows)
        await db.execute(stmt.on_conflict_do_update(
            constraint="uq_news_items_source_external_id",
            set_={c: stmt.excluded[c] for c in ("title", "url", "impact", "impact_reason", "assets")}))
    return len(rows)


async def record_status(db: AsyncSession, result: FeedResult, now: datetime, kept: int) -> None:
    ok = result.error is None
    values = {"code": result.feed.code, "last_attempt_at": now, "last_ok_at": now if ok else None,
              "last_error": result.error, "items": kept if ok and not result.not_modified else None}
    stmt = pg_insert(NewsFeedStatus).values(values)
    update: dict[str, object] = {"last_attempt_at": now, "last_error": result.error}
    if ok:
        update["last_ok_at"] = now
        if not result.not_modified:
            update["items"] = kept
    await db.execute(stmt.on_conflict_do_update(index_elements=["code"], set_=update))


async def refresh_headlines(db: AsyncSession, source: HeadlineSource, feeds: Sequence[Feed], now: datetime,
                            keep_days: int) -> dict[str, int]:
    """Fetch, tag and store every feed; prune items older than ``keep_days``. Returns kept items per feed."""
    kept: dict[str, int] = {}
    for result in await source.fetch(feeds):
        n = await store_headlines(db, result.feed, result.items, now, keep_days) if result.items else 0
        await record_status(db, result, now, n)
        kept[result.feed.code] = n
    await db.execute(delete(NewsItem).where(NewsItem.published_at < now - timedelta(days=keep_days)))
    await db.commit()
    log.info("headlines_refreshed", **kept)
    return kept

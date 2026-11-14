"""Market Pulse: feed parsing (RSS, Atom, hostile input) and the impact / asset keyword rules."""

from __future__ import annotations

from datetime import UTC, datetime
from xml.etree.ElementTree import ParseError

import pytest

from app.services.news.classify import symbol_assets, tag
from app.services.news.headlines import clean_title, enabled_feeds, parse_feed

NOW = datetime(2026, 11, 15, 12, tzinfo=UTC)

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>
<item><title>Fed holds rates steady, signals patience</title><link>https://example.com/a</link>
  <guid>a-1</guid><pubDate>Sat, 14 Nov 2026 16:33:29 +0000</pubDate><description>long text</description></item>
<item><title><![CDATA[Bitcoin &amp; ether <b>slide</b> as liquidations hit $1B]]></title>
  <link>https://example.com/b</link><pubDate>Sat, 14 Nov 2026 10:00:00 GMT</pubDate></item>
<item><title>No link</title></item>
<item><title>Bad link</title><link>javascript:alert(1)</link></item>
<item><title>From the future</title><link>https://example.com/c</link>
  <pubDate>Mon, 1 Jan 2030 00:00:00 GMT</pubDate></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom"><title>x</title>
<entry><title type="html">ECB&#8217;s Lagarde: speech on monetary policy</title>
  <link rel="alternate" href="https://example.com/ecb"/><id>tag:ecb,1</id><updated>2026-11-13T08:20:00+01:00</updated>
</entry></feed>"""


def test_rss_items_are_parsed_cleaned_and_filtered() -> None:
    items = parse_feed(RSS, NOW)
    assert [i.title for i in items] == ["Fed holds rates steady, signals patience",
                                        "Bitcoin & ether slide as liquidations hit $1B", "From the future"]
    assert items[0].published_at == datetime(2026, 11, 14, 16, 33, 29, tzinfo=UTC)
    assert items[2].published_at == NOW  # a future date is clamped to now
    assert items[0].external_id != items[1].external_id and len(items[0].external_id) == 40


def test_atom_entries_are_parsed() -> None:
    (item,) = parse_feed(ATOM, NOW)
    assert item.title == "ECB’s Lagarde: speech on monetary policy" and item.url == "https://example.com/ecb"
    assert item.published_at == datetime(2026, 11, 13, 7, 20, tzinfo=UTC)


def test_external_entities_are_not_resolved() -> None:
    evil = b"""<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]>
<rss><channel><item><title>&x;</title><link>https://e.com</link></item></channel></rss>"""
    with pytest.raises(ParseError):
        parse_feed(evil, NOW)


@pytest.mark.parametrize(("title", "impact", "assets"), [
    ("Fed holds rates steady, signals patience", "high", {"USD"}),
    ("BoE cuts interest rates to 3.5%", "high", {"GBP"}),
    ("US CPI rises 0.4% in October, above forecasts", "high", {"USD"}),
    ("Exchange halts withdrawals after $40M hack", "high", set()),
    ("SEC approves spot Solana ETF", "high", {"SOL", "CRYPTO"}),
    ("Lagarde speech: ECB stays data-dependent", "medium", {"EUR"}),
    ("UK retail sales fall more than expected", "medium", {"GBP"}),
    ("Bitcoin slides to 3-month low of $65,000", "medium", {"BTC", "CRYPTO"}),
    ("Gold price forecast: XAU/USD eyes $4,200", "low", {"XAU", "USD"}),
    ("Here's what happened in crypto today", "low", {"CRYPTO"}),
    ("Federal Reserve Board announces pricing for payment services", "low", {"USD"}),
    ("Japan's yen weakens past 160 as BoJ stays put", "low", {"JPY"}),
])
def test_impact_and_asset_rules(title: str, impact: str, assets: set[str]) -> None:
    t = tag(title)
    assert t.impact == impact, (title, t.reason)
    assert assets <= set(t.assets), (title, t.assets)


def test_us_pronoun_is_not_the_dollar_and_defaults_come_first() -> None:
    assert "USD" not in tag("Tell us what you think about stablecoins").assets
    assert tag("Monetary policy statement", ("EUR",)).assets[0] == "EUR"
    assert tag("Monetary policy statement").impact == "high"


def test_symbol_assets() -> None:
    assert symbol_assets("fx", "EUR", "USD") == {"EUR", "USD"}
    assert symbol_assets("crypto", "BTC", "USDT") == {"BTC", "CRYPTO", "USD"}
    assert symbol_assets("metal", "XAU", "USD") == {"XAU", "USD"}
    assert symbol_assets("commodity", "WTI", "USD") == {"OIL", "USD"}


def test_clean_title_and_enabled_feeds() -> None:
    assert clean_title("  A <i>b</i>\n &amp; c ") == "A b & c"
    assert [f.code for f in enabled_feeds(["ecb", "nope"])] == ["ecb"]
    assert len(enabled_feeds([])) >= 9

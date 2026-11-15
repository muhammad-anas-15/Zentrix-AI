"""Impact tag and asset badges for a news headline, by published keyword rules.

The impact tag ranks the *type* of news (a rate decision or a CPI release is High, a speech or a PMI is Medium,
analysis and opinion are Low). It says nothing about the size or direction of a price move. Assets are the
currencies, metals, energy and coins a headline names. Rules are deliberately simple and listed in full here so
the tag can be explained to a user.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

METHOD = ("Impact tags on headlines come from keyword rules on the headline text: central-bank rate decisions, "
          "tier-1 data (CPI, payrolls, GDP), exchange hacks or halts, ETF decisions, lawsuits by regulators, "
          "sanctions or war are High; central-bank speeches and minutes, second-tier data and large market moves "
          "are Medium; analysis, outlooks and everything else are Low. A tag ranks the type of news, not the size "
          "or direction of a price move. Calendar events keep the impact their publisher gives them.")


def _w(*words: str) -> re.Pattern[str]:
    """Case-insensitive whole words/phrases."""
    return re.compile(r"\b(?:" + "|".join(words) + r")\b", re.IGNORECASE)


def _a(*acronyms: str) -> re.Pattern[str]:
    """Case-sensitive acronyms (so "US" is not "us")."""
    return re.compile(r"(?<![A-Za-z])(?:" + "|".join(acronyms) + r")(?![A-Za-z])")


# Asset code -> patterns. Codes match instrument bases/quotes (USD, EUR, XAU, BTC, ...); OIL covers WTI and Brent.
ASSETS: dict[str, tuple[re.Pattern[str], ...]] = {
    "USD": (_w("fed", "fomc", "federal reserve", "powell", "dollar", "greenback", "treasur(?:y|ies)",
               "non-?farm", "payrolls", "wall street", "white house", "trump"),
            _a("US", "U\\.S\\.", "USD", "DXY", "NFP", "PCE")),
    "EUR": (_w("euro", "eurozone", "euro area", "ecb", "european central bank", "lagarde", "schnabel",
               "germany", "german", "france", "french", "italy", "europe"),
            _a("EUR", "EU", "ECB")),
    "GBP": (_w("pound", "sterling", "bank of england", "bailey", "britain", "british", "gilts?"),
            _a("GBP", "UK", "BoE", "BOE")),
    "JPY": (_w("yen", "bank of japan", "ueda", "japan", "japanese", "jgbs?"), _a("JPY", "BoJ", "BOJ")),
    "CHF": (_w("swiss franc", "swiss national bank", "switzerland"), _a("CHF", "SNB")),
    "AUD": (_w("aussie", "reserve bank of australia", "australia", "australian"), _a("AUD", "RBA")),
    "NZD": (_w("kiwi", "reserve bank of new zealand", "new zealand"), _a("NZD", "RBNZ")),
    "CAD": (_w("loonie", "bank of canada", "canada", "canadian"), _a("CAD", "BoC", "BOC")),
    "CNY": (_w("yuan", "renminbi", "china", "chinese", "beijing"), _a("CNY", "CNH", "PBoC", "PBOC")),
    "INR": (_w("indian rupee", "reserve bank of india", "india", "indian", "sensex", "nifty"), _a("INR", "RBI")),
    "PKR": (_w("pakistani? rupee", "state bank of pakistan", "pakistan", "pakistani"), _a("PKR", "SBP")),
    "XAU": (_w("gold", "bullion"), _a("XAU")),
    "XAG": (_w("silver"), _a("XAG")),
    "OIL": (_w("oil", "crude", "brent", "opec\\+?"), _a("WTI", "OPEC")),
    "BTC": (_w("bitcoin"), _a("BTC")),
    "ETH": (_w("ether", "ethereum"), _a("ETH")),
    "SOL": (_w("solana"), _a("SOL")),
    "XRP": (_w("ripple"), _a("XRP")),
    "BNB": (_w("bnb chain", "binance coin"), _a("BNB")),
    "DOGE": (_w("dogecoin"), _a("DOGE")),
    "ADA": (_w("cardano"), _a("ADA")),
    "AVAX": (_w("avalanche"), _a("AVAX")),
    "LINK": (_w("chainlink"), _a("LINK")),
    "CRYPTO": (_w("crypto", "cryptocurrenc(?:y|ies)", "stablecoins?", "altcoins?", "defi", "blockchain", "tokens?",
                  "web3", "memecoins?", "binance", "coinbase"),),
}
COINS = frozenset({"BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "ADA", "AVAX", "LINK"})

# Analysis and opinion are Low whatever they mention (checked first).
OPINION = _w("price (?:prediction|forecast|analysis)", "forecast:", "technical analysis", "what i'?m watching",
             "outlook", "explained", "how to", "opinion", "podcast", "newsletter", "sponsored", "guide",
             "(?:market|news) wrap", "recap", "week ahead", "here'?s what happened", "chart of the")

# (impact, reason, pattern) in priority order.
RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("high", "central-bank rate decision", _w(
        "rate decision", "interest rate decision", "(?:raises|hikes|cuts|lowers|holds|keeps|leaves|maintains) "
        "(?:its )?(?:key |benchmark |policy |interest )*rates?", "rates? (?:unchanged|on hold)",
        "monetary policy (?:decision|statement|announcement)", "fomc statement", "emergency (?:meeting|cut|hike)")),
    ("high", "tier-1 economic data", re.compile(
        r"(?<![A-Za-z])(?:CPI|NFP|GDP|PCE)(?![A-Za-z])|\b(?:non-?farm payrolls|jobs report|consumer price index|"
        r"inflation (?:rate|data|report|figures?))\b", re.IGNORECASE)),
    ("high", "exchange or protocol incident", _w(
        "hack(?:ed|s)?", "exploit(?:ed|s)?", "breach", "drained", "(?:halts|suspends|pauses|freezes) "
        "(?:all )?(?:withdrawals|deposits|trading)", "bankrupt(?:cy)?", "insolven(?:t|cy)", "collapse[sd]?",
        "delist(?:s|ing|ed)?", "depeg(?:s|ged)?")),
    ("high", "regulator or ETF decision", _w(
        "etf (?:approv\\w*|reject\\w*|denied|launch\\w*)", "approves? (?:\\w+ )?etf", "sec (?:sues|charges|approves|"
        "rejects|denies)", "(?:sues|charges) (?:binance|coinbase|kraken)", "ban(?:s|ned)? (?:crypto|bitcoin)")),
    ("high", "geopolitical shock", _w(
        "war", "invasion", "invades", "missile", "airstrikes?", "ceasefire", "sanctions?", "tariffs?",
        "default(?:s|ed)?", "martial law", "coup")),
    ("medium", "central-bank speech or minutes", _w(
        "speech", "speaks", "remarks", "testimony", "testifies", "minutes", "press conference",
        "monetary policy report", "financial stability report", "rate (?:hike|cut)s?", "hawkish", "dovish",
        "forward guidance", "quantitative (?:easing|tightening)", "balance sheet")),
    ("medium", "economic data", re.compile(
        r"(?<![A-Za-z])(?:PMI|PPI|ISM)(?![A-Za-z])|\b(?:retail sales|jobless claims|unemployment|trade balance|"
        r"consumer confidence|industrial production|housing starts|employment|wages|inflation|yields?)\b",
        re.IGNORECASE)),
    ("medium", "large market move", _w(
        "surges?", "soars?", "plunges?", "plummets?", "crash(?:es|ed)?", "tumbles?", "slides?", "sinks?",
        "rall(?:y|ies)", "record high", "all-time high", "liquidations?", "sell-?off", "capitulation",
        "(?:\\d+(?:\\.\\d+)?)% (?:drop|fall|jump|gain|surge|plunge)")),
    ("medium", "market structure", _w(
        "will list", "lists", "listing", "etf (?:inflows|outflows|flows)", "regulation", "regulators?",
        "(?:crypto|stablecoin|market structure|digital asset) (?:bill|law|act)", "stablecoins?")),
)


@dataclass(frozen=True)
class Tagged:
    impact: str
    reason: str
    assets: tuple[str, ...]


def tag(title: str, default_assets: tuple[str, ...] = ()) -> Tagged:
    """Impact and assets of one headline. ``default_assets`` come from the source (e.g. the ECB feed: EUR)."""
    found = [code for code, patterns in ASSETS.items() if any(p.search(title) for p in patterns)]
    if any(c in COINS for c in found) and "CRYPTO" not in found:
        found.append("CRYPTO")
    assets = tuple(dict.fromkeys([*default_assets, *found]))
    if OPINION.search(title):
        return Tagged("low", "analysis or opinion", assets)
    for impact, reason, pattern in RULES:
        if pattern.search(title):
            return Tagged(impact, reason, assets)
    return Tagged("low", "no rule matched", assets)


def symbol_assets(asset_class: str, base: str, quote: str) -> frozenset[str]:
    """Assets whose news reaches an instrument: FX both currencies, metals/commodities the asset and its quote
    currency, crypto the coin and crypto-wide news (plus USD macro, like the news guard)."""
    if asset_class == "crypto":
        return frozenset({base, "CRYPTO", "USD"})
    if asset_class == "commodity" and base in ("WTI", "BRENT"):
        return frozenset({"OIL", quote})
    return frozenset({base, "USD" if quote == "USDT" else quote})

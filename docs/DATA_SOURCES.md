# Data sources: history plan and provider terms

## 1. Current sources

| Data | Provider | Used for | Notes |
|---|---|---|---|
| Forex + gold candles | Twelve Data REST (`time_series`) | training, live signals | Free plan: 8 req/min, 800 req/day, <=5000 candles/call. Timestamps requested in UTC. |
| Crypto candles | Binance USD-M futures klines (public) | research models only | No key. Product targets forex and gold. |
| Economic calendar | `nfs.faireconomy.media` (ForexFactory weekly JSON) | news guard, news alerts, journal review | Unofficial feed, no published terms or SLA. Worker fetches it hourly into `news_events`. |
| Live chart candles | Binance spot / USD-M public klines (`/v1/candles/live`) | the forming candle on crypto charts | Fetched on demand, cached 1 s per series (one request in flight). FX and metals have no ticks on the free Twelve Data plan: their charts update at each close. |
| Headlines (Market Pulse) | RSS/Atom: Fed, ECB, Bank of England, Bank of Japan, U.S. SEC (official); FXStreet, investingLive, CoinDesk, Cointelegraph (publishers) | Pulse tab, Home preview | Worker polls every 2 min with ETag/Last-Modified. Title, link, source and time only, never article text. Impact and asset tags come from keyword rules (`app/services/news/classify.py`). `NEWS_FEEDS` turns feeds on or off. RBI and SBP block automated access (403). Social posts (X) are not included: they need a paid API. |

## 2. Forex history (CLAUDE.md item 5)

**Done in Phase 0**
- Twelve Data history is paged backwards with `end_date` (verified on the free plan: each call returns another
  5000 candles further back). The pipeline now trains on 12 months of 15m/5m, 24 months of 1h and 3 months of 1m,
  instead of one call (~7 weeks of 15m).
- Local parquet cache (`backend/data_cache/`, gitignored) so history is fetched once and extended incrementally;
  `python -m ml.training.pipeline --offline` reuses it with no API calls.
- `ml.data.history.import_csv(path, symbol, interval)` merges offline exports (columns: `time` = candle open time
  in UTC, `open, high, low, close[, volume]`) into the same cache.

**Options for longer history (research/training only, never on the Linux server)**

| Option | Depth | Cost | Caveats |
|---|---|---|---|
| Twelve Data paging (current) | Varies by symbol/interval; 1m is the shallowest | Free plan calls | Free plan is internal, non-display use only (see 3). |
| MetaTrader 5 Python package (`MetaTrader5`) + broker demo account | Years of M1-H1 | Free | Windows-only; broker-specific prices (spreads, server timezone; convert to UTC on export). Export to CSV, then `import_csv`. |
| HistData.com / Dukascopy historical downloads | Many years of M1/tick | Free | Check each site's terms for model training; different price feed than live (bid vs mid). |
| Paid Twelve Data plan | Longer intraday depth, higher rate limits | Paid | Same feed as live: best train/serve consistency. |

**Recommendation:** train on the same feed that serves live signals (Twelve Data) where possible. If MT5 or
HistData is used for depth, keep a Twelve Data out-of-sample period to check the model still holds on the live feed.

## 2b. Live ingestion budget (Phase 2 worker)

- **Twelve Data free plan:** 8 requests/min and 800/day. One request per (instrument, timeframe) per candle close:
  6 instruments x (15m + 1h) is ~720 requests per weekday. The worker enforces a daily budget
  (`TWELVE_DATA_DAILY_BUDGET`, default 780) and runs nothing below 15m live. Requests are 8 s apart, so the
  last FX series of a quarter-hour is fetched ~100 s after the close (inside the 3-minute signal window).
  More pairs or faster timeframes need a paid plan; enabling them is an `ingestion_targets` row, not code.
- **Chart timeframes (Phase 5.7):**
  - FX/gold 4h is built by the worker from the stored 1h candles (`ingestion_targets.derive_from = '1h'`), at no
    request cost.
  - 1d is fetched for all 20 FX/gold markets: about 20 requests a day, about 740 in total. Those targets have
    priority 900, so they run after the signal series of a tick.
  - FX/gold 5m would need about 1,700 requests a day and is not ingested on the free plan; the app explains this.
- **Binance:** public klines, no daily budget at this volume (well under the request-weight limits). Crypto has
  every chart timeframe: 5m, 15m, 1h, 4h and 1d.

## 3. Provider terms (CLAUDE.md item 10). Blocking for launch, not for research

Checked 2026-11-12. Verify again before launch; terms change.

- **Twelve Data:** the pricing page lists the free Basic plan as "internal non-display usage only"; individual
  plans are for "personal, internal, and non-commercial use". **External display** first appears on
  **Venture ($149/mo)**; **external distribution** on **Enterprise ($1,099/mo)**. So the current key may be used for
  research and training, but **not to show prices, charts or (likely) derived signals to app users**. Whether
  signals derived from the data count as display needs written confirmation from Twelve Data.
  Sources: <https://twelvedata.com/pricing>, <https://twelvedata.com/terms> (dated 2020-10-24),
  <https://support.twelvedata.com/en/articles/5332349-commercial-and-personal-usage>,
  <https://support.twelvedata.com/en/articles/12647398-attribution-guidelines-for-using-twelve-data>.
- **Binance:** no explicit public policy found for showing public market data in a commercial third-party app.
  A developer-forum reply calls it "presumed" fair use, which is not a licence. Read section III of the current
  Binance Terms of Use and ask Binance in writing before any user-facing crypto data.
  Sources: <https://dev.binance.vision/t/public-rest-api-for-commercial-use-case/23067>,
  <https://data.binance.vision/Binance_Vision-Terms_of_Use.pdf>.
- **ForexFactory calendar feed:** unofficial endpoint. Replace with a licensed calendar before launch.
- **Headline feeds (added 2026-11-15):** central-bank and SEC feeds are official public releases. Publisher RSS
  feeds (FXStreet, investingLive, CoinDesk, Cointelegraph) are offered for reading; showing them in a commercial
  app needs each publisher's permission, or a licensed news API. Until confirmed, keep them for testing, or
  set `NEWS_FEEDS=fed,ecb,boe,boj,sec` for a public build.

**Decision needed before Phase 2 goes public:** budget a display-licensed forex/gold feed (for example Twelve Data
Venture, or another provider with display rights), or keep signals internal until then.

# Phase 5.6: live chart, Market Pulse, flagship polish

Branch `phase-5.6` (from `phase-5.5`). Requested before Phase 6: a TradingView-style live chart, a news and
market-pulse section, and a flagship-grade visual pass over every screen.

## Decisions and assumptions

1. **Live chart: real ticks where the data allows it.**
   - Crypto (Binance listings): `GET /v1/candles/live` proxies Binance's public klines. It returns the forming
     candle plus the one that just closed, cached for 1 s per series with a single fetch in flight, under its own
     rate-limit bucket. The app polls every 2 s while a chart is open and animates between updates (TradingView
     shows exchange ticks; a 2 s poll with tweening looks the same at phone scale).
   - FX and metals (Twelve Data free plan): ingestion already uses about 720 of the 800 daily calls, and the paid
     feed is on hold, so there are no ticks. Those charts show the candle-close countdown and add each candle when
     it closes, labelled "Updates at candle close". No fake ticks.
2. **Market Pulse: a new tab.**
   - Sources:
     - official central-bank feeds: Fed, ECB, BoE, BoJ;
     - SEC press releases (only the market-relevant ones);
     - headline RSS feeds from FXStreet, investingLive, CoinDesk and Cointelegraph. Each item shows its title,
       source, time and a link out, never the article text;
     - the economic calendar we already ingest.
   - The worker polls the feeds every 2 min, sending ETag/Last-Modified headers.
   - Impact tags:
     - calendar events keep the publisher's impact rating;
     - headlines get High/Medium/Low from published keyword rules (the method text is in the API). This rates
       how important the news type is, not how price will react.
   - Asset badges (USD, EUR, ..., XAU, BTC, ETH) come from keyword rules too.
   - Not included:
     - social posts (X/Twitter) need a paid API, the data budget is on hold, and scraping breaks X's terms;
     - RBI and SBP block automated access (403).
   - Before launch: confirm each publisher's terms for commercial display, or switch to a licensed news API
     (docs/DATA_SOURCES.md).
3. **Navigation.** Five tabs: Home, Markets, Pulse, Risk, Journal. Settings moves to a profile button in the
   app bar; the `/settings` route is unchanged.
4. **Polish across all screens.**
   - Pair view: chart first, with a live price header and tabs for Signal, Levels, Conditions and News.
   - Chart:
     - volume histogram and time axis;
     - crosshair with price and time tags;
     - stop and target zones;
     - a jump-to-latest button.
   - Markets: rows with live prices and changes.
   - Calculator: a price ladder.
   - Journal: an equity curve.
   - Track record: a confidence band.
   - Throughout:
     - a sign-in hero and consistent page headers;
     - a motion pass that respects reduced motion.
5. **Honesty rules unchanged.**
   - No direction calls on Home or Pulse.
   - Impact tags are labelled as rules.
   - FX charts never pretend to be live.

## Verification

- **Backend tests:**
  - live candle: fake fetcher, cache and single flight, non-live fallback, closed market, rate-limit bucket;
  - headline parsing (RSS and Atom), classifier, store and dedup, pruning;
  - worker refresh and failures per feed;
  - `GET /v1/news/feed` filters.
- **App tests:**
  - merging live into stored candles;
  - chart countdown and live tag;
  - the Pulse screen (filters, badges, impact);
  - navigation (Pulse tab, settings button);
  - calculator ladder and journal curve rendering.
- Phone-size screenshots of the web build against live data (dark, light, Urdu).

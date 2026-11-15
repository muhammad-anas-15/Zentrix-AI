# Phase 5.7: every chart timeframe, and a 3-5 candle pattern projection

Branch `phase-5.7` (from `phase-5.6`).

## 1. Timeframes audit (local dev database, 2026-11-16)

| Venue | Ingested | Missing for the chart (5m, 15m, 1h, 4h, 1d) |
|---|---|---|
| Binance spot, 10 coins | 15m, 1h, 4h | 5m, 1d |
| Binance USD-M, 10 perps | 15m, 1h, 4h (+1m, 5m for one model) | 5m, 1d |
| Twelve Data, 6 FX/gold | 15m, 1h (+4h on one, for a model) | 5m, 4h, 1d |
| Twelve Data, 14 FX crosses | nothing | everything |

**Fix:**

- **Crypto:** ingest 5m and 1d from Binance. It is free and has no daily budget.
- **FX/gold, 4h:** build it from the stored 1h candles (worker aggregation, no API calls). A new
  `ingestion_targets.derive_from` marks such series.
- **FX/gold, 1d:** fetch it from Twelve Data for the 20 FX/gold markets. That is about 20 calls a day, which fits
  the free plan (~730 of 800 used today). These targets run after the signal series in each tick, so the midnight
  burst never delays 15m signals.
- **FX/gold, 5m: not possible on the free plan.** It needs about 1,700 calls a day, against a limit of 800 that
  live signals already mostly use.
  - The app shows each market's available timeframes (from the API) and says why 5m is missing, instead of an
    empty chart.
  - It becomes possible when the paid feed is approved.
- **API:** `GET /v1/instruments` returns `timeframes` per instrument (ingested or derived).

## 2. Pattern projection (3-5 candles)

**Endpoint:** `GET /v1/patterns?symbol=&timeframe=&steps=5` (Premium label `pattern_outlook`). It returns:

- **The pattern on the last closed candles.** Three White Soldiers / Three Black Crows, Bullish / Bearish
  Engulfing, Hammer and Shooting Star (pin bars), Doji. The one- and two-candle rules are the same as the ML
  feature detector.
- **Structure and momentum:**
  - trend regime (ADX);
  - swing structure (higher highs and lows, or lower);
  - RSI;
  - ATR.
- **Projection:** what happened after the same pattern in this market's stored history.
  - For each of the next k = 1..5 candles: the median close and its 20-80% band, plus median wicks, in ATR units
    scaled to the current ATR.
  - Drawn as ghost candles and a band to the right of the last candle.
  - With fewer than 30 past cases, it shows the typical range of any candle and says so.
- **Base rate:** how often price was on the pattern's side k candles later. It comes with the number of cases, a
  95% interval and the baseline for any candle. "Edge" is true only when the interval sits above the baseline.
  Without an edge, the app draws the projection in neutral grey and says the pattern was close to a coin flip.
- **Label:** "Technical Pattern Projection (based on historical candlestick & ATR behaviour)". Never called a
  prediction or a signal, and not on Home.

## Verification

- **Backend tests:**
  - pattern rules on built candles;
  - base rates on a series with a planted effect;
  - projection shape;
  - the endpoint, too-few-cases fallback, Premium gate;
  - derived 4h aggregation and the worker;
  - the instruments `timeframes` field.
- **App tests:**
  - timeframe chips follow the instrument;
  - Pattern tab text and labels;
  - chart projection renders.
- **Real data:** run the worker until the new series backfill, then check every timeframe on BTC, EUR/USD, XAU/USD
  and a cross, and the projection in the web build.

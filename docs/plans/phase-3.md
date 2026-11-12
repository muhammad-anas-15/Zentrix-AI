# Phase 3: trader-protection features

## Goal
Tools that help traders lose less, built on the Phase 2 data (stored closed candles, live signals, track
record): market-condition light, news guard, risk calculator, ATR stop/take-profit, exit advisor, scenario path,
journal, watchlists and push alerts.

**Accept (CLAUDE.md):** each feature has tests and an entry in `docs/API.md`.

## Deliverables
1. Migration 0004: `news_events`, `risk_profiles`, `journal_entries`, `watchlists`, `watchlist_items`, `alerts`,
   `alert_events`.
2. **News guard:** the worker fetches the economic calendar every hour into `news_events`. `GET /v1/news/events`
   and `GET /v1/news/guard?symbol=` return blackout/caution/clear for an instrument, with a countdown.
3. **Condition scorer:** `GET /v1/conditions?symbol=&timeframe=` returns a green/amber/red light. Inputs: trend
   vs range (ADX), volatility regime (ATR percentile), trading session and liquidity, news guard, data freshness.
   Every input is listed with the reason it contributed.
4. **Risk calculator:** `POST /v1/risk/position-size` returns size in units and lots, pip/point value, money at
   risk, reward and R:R, margin at a given leverage, and warnings. Currency conversion uses stored prices.
5. **ATR levels:** `GET /v1/levels` (any instrument/timeframe) and `GET /v1/signals/{id}/levels` return stop
   and targets as ATR multiples, nearest support/resistance, and a base rate: how often these exact levels were
   hit first on past stored candles.
6. **Exit advisor:** `POST /v1/exit-advice` (an open position): hold / tighten stop / take partial / consider
   exit, with reasons and an ATR trailing stop.
7. **Scenario path** (premium; gating comes in Phase 4): `GET /v1/scenario`. The next 1-5 candles as a price band
   with its measured coverage, plus direction probabilities only where a model exists, each with that model's
   live track record.
8. **Journal:** CRUD under `/v1/journal`, P&L and R-multiple computed by the server, stats, and a rule-based
   review. **Risk profile and risk status:** `/v1/me/risk-profile`, `/v1/me/risk-status` (daily loss limit,
   overtrading, loss streak, revenge-trade warnings).
9. **Watchlists:** CRUD and ordering, plus quotes per list (last closed price, 24h change, latest signal, news state).
10. **Alerts and push:** `/v1/devices` (FCM tokens) and `/v1/alerts` CRUD. Alert kinds: price cross, % move,
    signal (instrument or watchlist, minimum strength), news. Alerts are evaluated by the worker on each closed
    candle, new signal, and every minute for news. They are delivered as `alert_events` (an in-app inbox) and
    FCM pushes.
11. **WebSocket** `GET /v1/stream` carries public live events: closed candles and new signals.

## Assumptions (defaults; say if you want otherwise)
- **No new accuracy claims.** The tools are rules or statistics, and each response shows its method. Any "how
  often" figure is computed from stored data and labelled as what it is. Examples: a base rate for levels,
  measured band coverage for the scenario path, the live track record for model probabilities. Every response
  carries "Not financial advice".
- **Signals without a demonstrated edge are not used as evidence.** Today that is every live signal. The exit
  advisor and the scenario path show such a signal but say it is ignored. Signal alerts fire only at the
  user's minimum strength, and with the current models that strength never occurs.
- **News source:** the ForexFactory weekly JSON (this week and next week), fetched hourly. It is unofficial and
  has no licence, so it must be replaced before launch (DATA_SOURCES.md). RSS keyword headlines are no longer
  used for risk: the Reuters feed is dead and keyword hits were noise.
- **News windows:**
  - High impact: blackout from 30 min before to 30 min after the event.
  - Medium impact: caution from 15 min before to 15 min after.
  - A high-impact event within the next 2 hours puts the guard in caution.

  Events reach instruments through their currencies:
  - FX: base and quote currencies.
  - Metals and commodities: USD.
  - Crypto: USD, high-impact events only.
  - Events tagged "All": every instrument.
- **Condition thresholds:**
  - Trend: ADX(14) >= 25 is trending, <= 20 is ranging.
  - Volatility: the ATR(14)/price percentile over the last 500 candles. Below 20 is low, above 80 high,
    above 95 extreme.
  - Red: market closed, stale data, news blackout, or extreme volatility.
  - Amber: high volatility, news caution, or low-liquidity hours (the FX rollover around 17:00 New York, or
    Friday's last two hours).
  - Green: otherwise.
- **Risk calculator:**
  - Lots: FX lot = 100,000 units, XAU lot = 100 oz, XAG lot = 5,000 oz (`instruments.contract_size`). Lot step is
    0.01 by default; sizes are rounded **down** so risk never exceeds the input.
  - Pips: 0.0001 for FX, 0.01 for JPY-quoted pairs. Other assets use points (10^-decimals).
  - Conversion: quote-to-account currency uses the latest stored close of the direct or inverse pair, or a
    route via USD; the client can pass `conversion_rate` instead. USDT is treated as 1 USD, and the response
    says so.
  - Warnings: risk above 2% (above 5% is a strong warning), a stop tighter than 0.5 x ATR, R:R below 1, and
    risk over the remaining daily loss budget when signed in.
- **ATR levels:**
  - Stop = 1.5 x ATR(14); targets at 1R and 2R. All multiples are adjustable.
  - Base rate: on the last 1,000 stored candles, the share of entries in that direction where the target was hit
    before the stop within 50 candles. A candle that touches both counts as a loss (conservative).
- **Exit advisor rules:**
  - R-multiple so far.
  - Distance to stop and target in ATR.
  - Chandelier trailing stop: best price since entry minus 3 x ATR.
  - Close beyond the recent swing (structure break).
  - News blackout ahead, volatility spike, and an opposing signal (only if its model has a demonstrated edge).
- **Scenario path:**
  - Band = 10th-90th percentile of past k-candle close-to-close moves from the latest close, k = 1..5, last 1,000 stored
    candles.
  - Coverage is checked out of sample on the most recent 250 cases, each using only earlier data, and reported
    next to the nominal 80%.
- **Journal:**
  - Quantity in units; P&L in quote currency and account currency.
  - The account-currency rate is taken from stored prices at exit, or from `fx_rate` supplied by the client.
  - The review is rules over the user's own trades, for example: losers held longer than winners, trading in
    news blackouts, inconsistent risk, overtrading. Gemini wording is optional later; its key is pending
    rotation.
- **Risk status:** "Today" follows the user's timezone. Defaults:
  - 1% risk per trade;
  - 3% daily loss limit;
  - 6 trades per day;
  - 3 losses in a row trigger a warning;
  - a new trade within 15 minutes of a loss is flagged as a possible revenge trade.
- **Watchlists:** at most 20 lists and 100 items per list. Quotes are the last *closed* candle (with `as_of`);
  there is no tick feed yet.
- **Alerts:**
  - At most 50 active alerts per user.
  - Per-alert cooldown; one-shot alerts switch off after firing.
  - De-duplicated by (alert, trigger key).
  - Price alerts use the candle high/low, so a wick that crosses the level counts.
- **FCM** uses the HTTP v1 API with a service-account JSON (`FCM_CREDENTIALS_FILE`), with no firebase-admin
  dependency. Without credentials, pushes are logged and `alert_events` still records them, so this does not
  block the phase. Invalid tokens are deleted.
- **Access:** user data (journal, risk profile, watchlists, alerts, devices) needs sign-in. Calculators,
  conditions, news, levels, exit advice and scenario are public with the IP rate limit. Free/premium gating is
  Phase 4.

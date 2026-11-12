# Architecture: multi-asset, multi-venue

Scope: an **analysis and risk-tools app**. No order execution, no custody, no user exchange API keys.
"Binance integration" means market data (spot and USD-M futures). Not financial advice.

## 1. Coverage

| Asset class | Examples | Venue / feed today | Notes |
|---|---|---|---|
| FX majors and minors | EUR/USD, GBP/USD, USD/JPY, EUR/GBP, AUD/JPY | Twelve Data | Free plan is non-display (see DATA_SOURCES.md) |
| Precious metals | XAU/USD, XAG/USD, XPT/USD | Twelve Data (XAU only on free plan) | Silver/platinum need a paid or other feed |
| Commodities | WTI, Brent, natural gas, copper | none yet (`planned` listings) | Vendor decision before Phase 2 goes public |
| Crypto spot | BTC/USDT, ETH/USDT, SOL/USDT, BNB/USDT, XRP/USDT | Binance spot | Free public data; geo-restricted in some regions |
| Crypto perpetuals | BTC/USDT:PERP, ETH/USDT:PERP, ... | Binance USD-M futures | Separate instrument from spot (different price) |

Timeframes: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 1d, 1w (rows in a table, extendable without migration of data).

## 2. Data model (PostgreSQL 16)

Design rules, so new assets, venues and timeframes are inserts, not schema refactors:

1. **Instrument vs listing.** An *instrument* is what a user thinks about (EUR/USD, BTC/USDT perpetual).
   A *listing* is one venue's feed for it (Twelve Data `EUR/USD`, Binance spot `BTCUSDT`). Market data
   (candles, signals) references a **listing**; user objects (watchlists, alerts, journal) reference an
   **instrument**. Each instrument has at most one primary listing used by default.
2. **Timeframes are rows** (`timeframes.code` FK), not an enum.
3. **One instruments table for all asset classes.** Class-specific attributes are typed nullable columns
   (`settle`, `expiry`, `contract_size`) plus `meta` JSONB; no per-class tables.
4. **Market hours by session code** (`fx_24x5`, `crypto_24x7`, ...) implemented in code
   (`ml/data/sessions.py`), shared by ingestion, features, signals and alerts.
5. **Generic alerts**: `kind` text + `params` JSONB, validated per kind by Pydantic, so new alert types do not
   need columns.
6. Time is always `timestamptz` in UTC; candle `ts` is the candle **open** time.

### Built in Phase 1

| Table | Key columns |
|---|---|
| `venues` | `code` (unique: `binance_spot`, `binance_usdm`, `twelvedata`, ...), `name`, `kind` (exchange / data_vendor / broker) |
| `timeframes` | `code` PK, `seconds`, `sort_order` |
| `instruments` | `symbol` (unique canonical: `EUR/USD`, `BTC/USDT`, `BTC/USDT:PERP`), `asset_class`, `instrument_type` (spot / perpetual / future / cfd), `base`, `quote`, `settle`, `expiry`, `contract_size`, `price_decimals`, `session`, `meta`, `active` |
| `instrument_listings` | `instrument_id`, `venue_id`, `venue_symbol`, `status` (active / planned / restricted), `is_primary`, `note`; unique (`venue_id`, `venue_symbol`); one primary per instrument |
| `candles` | PK (`listing_id`, `timeframe`, `ts`), OHLC, `volume`, `quote_volume`, `trades`, `ingested_at`; **range-partitioned by month on `ts`** (`zx_ensure_candle_partitions()` creates partitions) |
| `users` | `id` UUID, `email`, `display_name`, `plan` (free / premium), `locale` (en / ur), `timezone` |
| `auth_identities` | (`provider`, `subject`) unique, `user_id` |
| `refresh_tokens` | `token_hash` (SHA-256, unique), `family_id` (rotation + reuse detection), `expires_at`, `revoked_at` |
| `devices` | `fcm_token` unique, `platform`, `user_id` |
| `subscriptions`, `entitlements` | entitlement model; billing not integrated (`PREMIUM_ENFORCED=false`) |
| `audit_log` | security events; survives account deletion without personal data |

### Designed now, migrated in the phase that builds them (additive migrations)

| Table | References | Phase |
|---|---|---|
| `model_versions` | `listing_id`, `timeframe`, `horizon`, `label_mode`, metrics/calibration JSON | 2 |
| `signals` | `listing_id`, `instrument_id`, `timeframe`, `candle_ts`, `model_version_id`; unique (`model_version_id`, `listing_id`, `candle_ts`) | 2 |
| `signal_outcomes` | `signal_id`, entry/exit per the model's `label_mode` | 2 |
| `watchlists`, `watchlist_items` | `user_id`; items -> `instrument_id`, `sort_order` | 3 |
| `alerts`, `alert_events` | `user_id`, `instrument_id`, optional `listing_id`/`timeframe`, `kind`, `params`, `cooldown_s`, `last_triggered_at` | 3 |
| `journal_entries` | `user_id`, `instrument_id`, side, qty, entry/exit price and time, fees, tags | 3 |
| `risk_profiles` | `user_id`, account currency, balance, risk %, daily loss limit | 3 |
| `news_events` | currency/country tags, impact, time; mapped to instruments via base/quote | 3 |

## 3. Market-data providers

One interface per venue (`fetch_range`, `fetch_latest`, `stream`, capabilities: timeframes, history depth,
display rights). The ingestion worker picks the provider from the listing's venue.

- **Binance spot** (`api.binance.com`, public data also at `data-api.binance.vision`) and **USD-M futures**
  (`fapi.binance.com`): REST klines + WebSocket kline/ticker streams. Binance blocks some regions (for example
  US IPs), so the server must be hosted in an allowed region. Display terms are unclear (DATA_SOURCES.md).
- **Twelve Data**: FX and gold now. Silver and commodities need a paid plan or another vendor; real-time
  WebSocket is paid.
- **Silver / commodities / real-time FX**: needs a vendor with display rights. Compare coverage, display
  licence, latency and price before Phase 2 goes public. Adding it is a new `venues` row, listings and a provider
  class. No schema change.
- **MT5**: offline research data only (Windows); never on the server.

## 4. Real-time, alerts and app features

| Feature (as in TradingView / Binance / MT5 apps) | Backend support | Phase |
|---|---|---|
| Interactive candlestick charts, any timeframe | `GET` candles by listing + timeframe (cursor paging); live updates over WebSocket | 2 / 5 |
| Fast watchlists with live prices | watchlist tables; Redis-cached last price per listing; WebSocket fan-out | 3 |
| Price / % move / signal-threshold alerts | alert evaluator on each closed candle and ticker update; FCM push with cooldown and dedupe | 3 |
| Position-size and risk calculator | pure service using `contract_size`, `price_decimals`, quote/account currency conversion | 3 |
| Journal and portfolio tracking | `journal_entries`; P&L in account currency | 3 |
| Market-condition light, news countdown | sessions, ATR regime, `news_events` | 3 |

Flow: provider -> ingestion worker (closed candles only, upsert into `candles`) -> Redis pub/sub
(`candles:{listing}:{tf}`) -> signal job + alert evaluator -> Postgres + FCM -> WebSocket to the app.

## 5. Compliance notes

- Analysis only: no trading, deposits or wallets. Play's crypto exchange/wallet policy targets those; keep the
  app clearly outside it. Do not market for binary options (CLAUDE.md section 9).
- Market-data display needs licensed feeds before launch (DATA_SOURCES.md).

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
| `users` | `id` UUID, `email`, `display_name`, `plan` (free / premium) + `plan_expires_at`, `is_admin`, `locale` (en / ur), `timezone` |
| `auth_identities` | (`provider`, `subject`) unique, `user_id` |
| `refresh_tokens` | `token_hash` (SHA-256, unique), `family_id` (rotation + reuse detection), `expires_at`, `revoked_at` |
| `devices` | `fcm_token` unique, `platform`, `user_id` |
| `subscriptions`, `entitlements` | entitlement model (section 6); billing not integrated (`PREMIUM_ENFORCED=false`). Entitlements = time-boxed grants (`key` = `premium` or one feature, `source`, `starts_at`, `ends_at`, `note`, `granted_by`) |
| `audit_log` | security events; survives account deletion without personal data |

### Built in Phases 2 and 3 (additive migrations 0003, 0004; Phase 4 added columns in 0005)

| Table | References | Phase |
|---|---|---|
| `model_versions` | `listing_id`, `timeframe`, `horizon`, `label_mode`, metrics/calibration JSON | 2 |
| `signals` | `listing_id`, `instrument_id`, `timeframe`, `candle_ts`, `model_version_id`; unique (`model_version_id`, `listing_id`, `candle_ts`) | 2 |
| `signal_outcomes` | `signal_id`, entry/exit per the model's `label_mode` | 2 |
| `watchlists`, `watchlist_items` | `user_id`; items -> `instrument_id`, `sort_order` | 3 |
| `alerts`, `alert_events` | `user_id`, `instrument_id` or `watchlist_id`, `timeframe`, `kind`, `params` (JSONB, validated per kind), `recurring`, `cooldown_s`; events unique per (alert, dedupe key), delivery state = push outbox and in-app inbox | 3 |
| `journal_entries` | `user_id`, `instrument_id`, side, qty, entry/exit price and time, stop/target, fees, tags; server-computed `pnl_quote`, `pnl_account`, `r_multiple`, `risk_account` | 3 |
| `risk_profiles` | `user_id` (PK), account currency, balance, risk %, daily loss %, max trades/day, loss-streak limit, leverage | 3 |
| `news_events` | source + external id (unique), currency, impact, `event_at`; mapped to instruments via base/quote (`app/services/news/guard.py`) | 3 |

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
| Fast watchlists with prices | watchlist tables; quotes from the last closed candle; WebSocket `candle` events (tick prices need a streaming feed) | 3 |
| Price / % move / signal / news alerts | alert evaluator on each closed candle, new signal and worker tick; FCM push with cooldown and dedupe | 3 |
| Position-size and risk calculator | pure service using `contract_size`, `price_decimals`, quote/account currency conversion | 3 |
| Journal and portfolio tracking | `journal_entries`; P&L in account currency | 3 |
| Market-condition light, news countdown | sessions, ATR regime, `news_events` | 3 |
| Free / Premium tiers (no payments) | feature registry + entitlement resolution + gate dependency (section 6) | 4 |

Flow: provider -> ingestion worker (closed candles only, upsert into `candles`) -> signal job + outcome resolver +
alert evaluator -> Postgres (`alert_events` outbox) -> FCM; candle and signal events -> Redis pub/sub (`zx:events`)
-> WebSocket `/v1/stream` to the app. The worker also refreshes the economic calendar hourly.

## 5. Compliance notes

- Analysis only: no trading, deposits or wallets. Play's crypto exchange/wallet policy targets those; keep the
  app clearly outside it. Do not market for binary options (CLAUDE.md section 9).
- Market-data display needs licensed feeds before launch (DATA_SOURCES.md).

## 6. Plans and entitlements (Phase 4, no payments)

- **One feature registry** (`app/services/entitlements.py`, `FEATURES`): every product feature with its tier.
  Gates, response labels, `GET /v1/plans` and the docs come from it.
- **Effective access** (`resolve_access`) = any of: `users.plan = premium` (not past `plan_expires_at`), an
  `active`/`grace` subscription, or an active `entitlements` grant (`premium`, or one feature key). It is computed
  per request, so expiry needs no job.
- **The gate** (`app/api/premium.py`):
  - `**premium("scenario")` on a route adds `require_premium` and the OpenAPI mark `x-premium`.
  - Partly premium routes take `GateDep` and call `gate.allows()` / `gate.require()`.
  - While `PREMIUM_ENFORCED=false`, the gate parses no token and runs no query.
  - When enforced: anonymous callers get 401, users without access get 403 `premium_required`.
- **Never locked:** reading, pausing and deleting a user's own data, account deletion, and the public track record
  (resolved signals of every market, and `/v1/track-record`).
- **Admins:** `users.is_admin` is set only by the server CLI (`python -m scripts.admin`). The `/v1/admin`
  endpoints set plans and grants and write `audit_log`.
- **Adding billing later:**
  - a store webhook writes `subscriptions` rows;
  - `resolve_access` already counts them;
  - flip `PREMIUM_ENFORCED=true`.

  No endpoint changes.

## 7. Mobile app (Phase 5)

Flutter (`mobile/`, see `mobile/README.md`).

- **Layers per feature:** `domain` (freezed models of the API payloads), `data` (repositories over one `ApiClient`),
  `application` (Riverpod notifiers and providers), `presentation` (screens and widgets).
- **Session:**
  - Tokens live in secure storage; `/v1/me` restores the session.
  - The dio interceptor refreshes once per burst of 401s and retries through an interceptor-free client.
  - A rejected refresh signs the user out.
- **Navigation:** go_router redirects by session state (restoring, signed out, guest, signed in). A deep link opened
  at start-up is kept and opened afterwards.
- **Design tokens:** `lib/core/theme/tokens.dart` is the only source of colours, spacing, radii and type, and a test
  enforces it. Claude Design output plugs in there.
- **Premium:** `premium` labels from the API are shown as badges. A `403 premium_required` becomes a "not on your
  plan" card; there is no paywall.
- **Developer sign-in** (`POST /v1/auth/dev`, dev/test only) lets the app run end to end before the Google OAuth
  client IDs exist.


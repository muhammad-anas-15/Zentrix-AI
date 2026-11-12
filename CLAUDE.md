# Zentrix: AI Trading Assistant (project brief for Claude Code)

## 1. Product
A trading *assistant* for forex and gold traders (not an oracle). It gives a direction signal with a calibrated
confidence, explains why (candle pattern, indicators, news, book knowledge), and helps traders lose less
(risk tools, news guard, market-condition check, exit advice). Free tier attracts users; premium tier is paid.
Target: Android app on Google Play, Flutter frontend, FastAPI backend, PostgreSQL.

**Honesty rule (non-negotiable):** never hardcode, invent, or market an accuracy number. Every accuracy figure shown
anywhere (UI, docs, store listing) must come from the out-of-sample track-record data in the database.
Never promise profit. Always show "Not financial advice".

## 2. What already exists (research code in repo root)
- `data_pipeline/`: `fetch_binance.py` (Binance Futures klines, paginated history), `fetch_forex.py` (Twelve Data).
- `features/`: `indicators.py`, `patterns.py`, `support_resistance.py`, `feature_builder.py`, `multi_timeframe.py`.
- `ml_model/`: `dataset_builder.py`, `train.py`, `backtest.py`, `evaluate.py`, `model_registry/*.pkl`
  (XGBoost; pickle = {"model","feature_cols"}; filename `{SYMBOL with / -> _}_{interval}[_h5]_xgb.pkl`).
  Label = next candle (or candle t+5 for `_h5`) closes above current close.
- `knowledge_base/`: 48-entry `source_docs/trading_knowledge.json`, Chroma + all-MiniLM-L6-v2, `retriever.py` (exact pattern
  lookup + semantic search + opposite-direction noise filter + force RSI entry when RSI>70 or <30).
- `news_layer/`: RSS + ForexFactory weekly calendar JSON + keyword risk flags.
- `orchestrator/agent.py`: `run_assistant(symbol, interval, use_llm)` returns pattern, rsi, ml_signal, ml_confidence,
  signal_strength (Strong>=70, Good>=65, Moderate>=60, Weak>=55, else "Very Weak - Wait"), trend_next_5_candles,
  possible_target_up/down (resistance/support), knowledge_matches, news_risk_level, explanation (Gemini, optional).
- `demo_tradding_logger/` (typo in folder name): historical simulator + accuracy report (SQLite).
- `check_signal.py`: CLI helper. Symbols with "/" are forex (Twelve Data), others are crypto (Binance).
- Trained: forex EUR/USD, GBP/USD, USD/JPY, AUD/USD, NZD/USD, GBP/JPY, USD/CAD, USD/CHF, XAU/USD (15m; some 1m/5m/1h),
  crypto BTCUSDT (1m/5m/15m/1h). Silver (XAG/USD) is not on the Twelve Data free plan.

## 3. Known problems: fix in Phase 0 before building anything on top
1. **Lookahead leak** in `multi_timeframe.build_higher_tf_series`: the higher-TF candle's close is used before that
   candle has closed. Use only fully closed higher-TF candles (shift by one higher-TF bar).
2. **In-sample evaluation**: `historical_simulator.py` scores the model on data it was trained on, so the reported
   ~60% and 83-89% high-confidence accuracy are inflated. Replace with strict walk-forward, out-of-sample predictions only.
   Earlier honest numbers: about 52-58% single-pair accuracy; EUR/USD 1m showed 86% on a split vs 65% walk-forward (overfit).
3. **Confidence is uncalibrated** and the strength thresholds were chosen from in-sample bands. Calibrate probabilities
   (isotonic or Platt) on out-of-sample data and derive strength labels from calibrated out-of-sample accuracy.
4. **Forming candle**: live fetch includes the still-open candle. Signals must be computed on the last *closed* candle only.
5. **Forex history is thin** (Twelve Data returns <=5000 candles per call, roughly 2 months of 15m). Plan a better history source
   for training. MT5 Python package is Windows-only, so use it only for offline research/training on a Windows machine, never on the Linux server.
6. Feature parity between training and inference (one-hot `pattern_`, `prev1_/prev2_/prev3_`, `higher_tf_bullish`) must be covered by tests.
7. Dataset building is slow (recomputes indicators per window). Vectorize it.
8. Rename `demo_tradding_logger` to `demo_trading_logger`; remove the SQLite logger once Postgres tracking exists.
9. Secrets: API keys were exposed in terminal output. Assume the Twelve Data and Gemini keys are compromised; keep them out of git,
   read from env only, ship `.env.example`, and tell me to rotate them.
10. Check data-provider terms before showing market data to end users (a commercial/redistribution plan may be needed).

## 4. Target architecture (monorepo)
```
/backend
  app/            FastAPI (api/, core/, models/, schemas/, services/, workers/)
  ml/             data, features, training, calibration, inference (moved from root; importable package)
  knowledge/      knowledge_base content + retriever
  alembic/        migrations
  tests/
/mobile           Flutter app
/infra            docker-compose (api, worker, postgres, redis), Dockerfile, CI config, deploy notes
/docs             API.md, ML_REPORT.md (honest metrics), PLAY_STORE.md, runbook
```

## 5. Tech decisions (defaults; ask before deviating)
- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.x (async) + Alembic, Pydantic v2 settings, PostgreSQL 16, Redis (cache, rate limit,
  locks), APScheduler or Celery worker for per-candle-close jobs, structlog JSON logs, pytest + httpx, ruff + mypy.
- **Auth:** Flutter `google_sign_in` -> send Google ID token to `POST /auth/google` -> backend verifies it with Google's keys
  -> issues own short-lived JWT access token + rotating refresh token (stored hashed, revocable). Postgres is source of truth for users.
  No passwords. Support logout, logout-all, and **account deletion** (required by Play).
- **Mobile:** Flutter stable, Riverpod, go_router, dio (+ interceptors for refresh), freezed/json_serializable,
  flutter_secure_storage, Firebase Cloud Messaging for push, in_app_purchase for Play Billing, flutter_localizations (English + Urdu, RTL ready).
  Candlestick charts: pick one (Syncfusion needs a license eligibility check; otherwise a lightweight OSS candlestick package) and justify.
- **UI:** the visual design will come later from Claude Design. Build every screen against a central design-token layer
  (colors, type scale, spacing, radii in one theme file) and reusable widgets, so the design can be applied by changing tokens/widgets, not screens.
  Until the design arrives use a clean, minimal functional theme. Do not invent branding.
- **Realtime:** WebSocket (or SSE) for live signal updates; REST for everything else.
- **Billing: NOT in scope for now.** We are in build stage with no audience, so nothing is charged. Premium features are built and
  labeled "Premium" (tier flag + entitlement checks on the server), but every user can use them for free. Do not integrate Play Billing,
  payments, or paywalls yet. Keep the entitlement layer so billing can be added later without refactoring (a `plan` field on users,
  a `require_premium` dependency, and a global `PREMIUM_ENFORCED=false` setting that, when later set to true, locks premium to paying users).

## 6. Data model (PostgreSQL, minimum)
users, auth_identities (provider, subject), refresh_tokens, devices (fcm_token), subscriptions, entitlements,
instruments (symbol, type, provider_symbol, active), candles (instrument, tf, ts, ohlcv; unique per instrument+tf+ts),
model_versions (instrument, tf, horizon, trained_at, metrics_json, calibration_json, artifact_path, active),
signals (instrument, tf, candle_ts, direction, raw_prob, calibrated_prob, strength, pattern, features_json, model_version_id, created_at),
signal_outcomes (signal_id, resolved_at, outcome, price_move, horizon_candles), watchlists, alerts, journal_entries,
risk_profiles, news_events, audit_log. Index for hot queries. Everything migrated with Alembic.

## 7. Product features by tier
**Free:** market-condition light (trend/range, volatility, session, news), news countdown, position-size and risk calculator,
2-3 signals/day on 15m for a few pairs, short explanation, public track-record page (every signal + outcome).
**Premium:** all pairs and timeframes (1m-1h), real-time signals, push alerts for Strong/Good on watchlist, entry/stop/take-profit/
risk-reward per signal (ATR-based), exit advisor for an open position, scenario path (next 3-5 candles as probabilities, clearly
labeled with its real accuracy), full English/Urdu explanation, trade journal with AI review, daily-loss-limit and overtrading warnings.
Tier gating lives in the backend, but during the build stage premium is shown as a label/badge only and is unlocked for everyone
(`PREMIUM_ENFORCED=false`). Free-tier limits are likewise not enforced yet.

## 8. Phases (finish and verify each before starting the next; commit per phase)
**Phase 0: Audit, restructure, fix.** Repo restructure per section 4, git init + .gitignore, config/env, Dockerfile + compose,
fix section 3 issues, walk-forward + calibration, produce `docs/ML_REPORT.md` with honest out-of-sample metrics per pair/timeframe
and a reliability (calibration) table. *Accept:* tests for leakage and feature parity pass; the report is generated by a script, not typed by hand.
**Phase 1: Backend foundation + auth.** FastAPI skeleton, Postgres + Alembic, Google sign-in + JWT/refresh, users, entitlement model,
rate limiting, health checks, OpenAPI. *Accept:* auth flow works end to end with tests; account deletion works.
**Phase 2: Signal engine + track record.** Candle ingestion worker, per-candle-close signal job on closed candles, caching, signals and
outcome-resolver job writing to Postgres, endpoints for signals, history, public accuracy stats. *Accept:* signals appear without a user request;
outcomes resolve automatically; the accuracy endpoint matches the DB.
**Phase 3: Trader-protection features.** Condition scorer, news guard, risk calculator, ATR stop/take-profit, exit advisor, scenario path (premium),
journal, watchlists, alerts (FCM). *Accept:* each has tests and an API doc entry.
**Phase 4: Premium tiering (no payments).** Plan/entitlement model, `require_premium` dependency, `PREMIUM_ENFORCED` flag (default false),
"Premium" labels in API responses, admin endpoint to set a user's plan. No Play Billing, no paywall. *Accept:* with the flag false everything
is accessible; with it true, premium endpoints refuse free users (covered by tests). Billing is a later post-launch phase.
**Phase 5: Flutter app.** Architecture, Google login, dashboard, pair view with candles and signal card, risk calculator, journal, track record,
alerts, settings, account deletion (premium features show a "Premium" badge but are not locked; no paywall), English/Urdu. Functional theme driven by design tokens. *Accept:* runs on a real Android device against the local backend.
**Phase 6: Production hardening and release.** Security review (OWASP API), secrets management, structured logging, error tracking, metrics,
backups, CI (lint, tests, build), load test on signal endpoints, deployment guide, privacy policy and terms drafts, signed AAB,
Play Console checklist in `docs/PLAY_STORE.md`. *Accept:* clean staging deploy and a release build.

## 9. Compliance and store risks (flag, don't hide)
- Google Play restricts binary-options apps and requires accurate financial-product disclosures. Position the app as forex/gold analysis and risk tools.
  Do not market it for Quotex/binary options in the listing, UI, or screenshots.
- Required: privacy policy, Data safety form, in-app account deletion, financial-features declaration, no profit guarantees, visible disclaimers.
- Billing is deferred. When it is added later, confirm Play Console payout/merchant support for my country first.

## 10. How to work
- Start every phase by writing a short plan and listing assumptions. Ask me only about decisions that block you; otherwise pick the default and note it.
- Small commits with clear messages, one concern per commit. Never commit secrets or model artifacts without noting size/LFS.
- Write tests with the code (pytest for backend/ML, widget and unit tests for Flutter). Run the full test suite before declaring a phase done.
- Don't silently change model behavior: any retrain must update `model_versions` and the ML report.
- Keep responses and docs concise. Report what changed, how you verified it, and what is still open.

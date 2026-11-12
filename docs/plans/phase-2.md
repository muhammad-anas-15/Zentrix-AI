# Phase 2: signal engine, candle ingestion, live track record

## Goal
A worker ingests closed candles, generates a signal at every candle close for each active model, resolves
outcomes automatically, and the API serves candles, signals, history and live accuracy stats from Postgres.

**Accept (CLAUDE.md):** signals appear without a user request; outcomes resolve automatically; the accuracy
endpoint matches the DB.

## Deliverables
1. Migration 0003: `ingestion_targets`, `model_versions`, `signals`, `signal_outcomes`.
2. Market-data providers by venue (Binance spot + USD-M futures, Twelve Data), keyed by listing.
3. Worker (`python -m app.workers.main`): at each candle close it ingests due (listing, timeframe) targets,
   then runs the signal job and the outcome resolver for that series. Backfills missing history on start.
4. `python -m app.workers.register_models`: registers trained artifacts as `model_versions` (one active per
   listing/timeframe/horizon) and adds the ingestion targets they need (base + higher timeframe).
5. API: `GET /v1/candles`, `GET /v1/signals` (history with outcomes), `GET /v1/signals/latest`,
   `GET /v1/track-record` (live stats), `GET /v1/models` (active models + their out-of-sample backtest).
6. Redis caching: latest signal per series; track-record responses keyed by an outcome counter.

## Assumptions (defaults; say if you want otherwise)
- **Live-only signals.** A signal is stored only if generated within one timeframe of its candle's close.
  Backfilled or late candles never create signals, so the track record cannot contain hindsight.
- **Every active model emits signals**, including models without a demonstrated edge: they show
  "Very Weak - Wait". The live track record is how marginal models get confirmed or rejected.
- **Outcome = the model's label:** entry = open of candle t+1, exit = open of candle t+h+1 (open-to-open);
  up/down vs direction gives win/loss; equal = flat; a gap in data far beyond the horizon = void.
  Hit rate excludes flat and void, which are counted and shown.
- **Candles stored = closed, market-hours candles only** (same filter as training; weekend forex quotes are
  dropped). Market hours come from `instruments.session`, not from symbol formats.
- **Twelve Data free plan budget** (8 requests/min, 800/day): default targets are 6 instruments x (15m, 1h)
  = ~720 calls on a weekday, with a daily budget guard. Twelve Data timeframes below 15m are not run live (1m
  models are gated off anyway). A paid feed lifts this; it is configuration, not code.
- **Binance:** all 20 crypto listings x (15m, 1h, 4h) by default; more timeframes are rows in `ingestion_targets`.
- **Scheduler:** a small asyncio loop in one worker process; jobs are idempotent (unique keys + upserts) and
  guarded by a Redis lock, so running two workers is safe. No Celery/APScheduler dependency.
- **Serving refuses drift:** a model only serves if its artifact's `trained_at` equals the registered version.
- Signal/track-record endpoints are public for now; free/premium limits are Phase 4. WebSocket push is Phase 3
  (with watchlists and alerts).

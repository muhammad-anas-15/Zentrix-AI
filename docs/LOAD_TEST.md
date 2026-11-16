# Load test: signal and market endpoints (Phase 6)

**Script:** `backend/scripts/load_test.py`. It is closed-loop: N virtual users, each sends its next request as soon
as the last one returns. The request mix follows an app session:

| Endpoint | Share |
|---|---|
| latest signal | 25% |
| live candle | 20% |
| candles | 15% |
| signal history | 10% |
| track record | 10% |
| radar | 8% |
| news feed | 7% |
| conditions | 5% |

The symbols are spread over 5 FX/gold and 4 crypto markets.

## Setup (2026-11-16)

All on one Windows laptop: the load generator, the API, PostgreSQL 16 (pgserver, real data: 111k candles, 720
signals) and a Redis stand-in. The API ran like staging:
- `APP_ENV=staging`;
- 2 uvicorn workers;
- JSON logs;
- metrics on;
- rate limiting off (every request comes from one IP).

A production host runs only the server side, so treat these numbers as a floor.

## Results

| Users | Duration | Requests | Throughput | Errors | p50 | p95 | p99 |
|---|---|---|---|---|---|---|---|
| 10 | 30 s | 4,757 | 158 req/s | 0 | 45 ms | 211 ms | 312 ms |
| 50 | 60 s | 10,259 | 170 req/s | 0 | 166 ms | 881 ms | 1,443 ms |

Per endpoint at 50 users:

| Endpoint | req/s | p50 | p95 | p99 |
|---|---|---|---|---|
| signals/latest | 41.5 | 226 ms | 872 ms | 1,381 ms |
| candles/live | 34.6 | 294 ms | 970 ms | 1,422 ms |
| candles (300) | 26.2 | 164 ms | 806 ms | 1,215 ms |
| track-record | 16.8 | 64 ms | 189 ms | 287 ms |
| signals (history) | 16.3 | 222 ms | 853 ms | 1,244 ms |
| radar | 13.9 | 98 ms | 1,363 ms | 3,040 ms |
| news/feed | 12.4 | 202 ms | 831 ms | 1,306 ms |
| conditions | 8.5 | 277 ms | 980 ms | 1,535 ms |

## Reading

- **No errors, and no request stalled behind another.** Before Phase 6 one levels or radar computation blocked an
  API process for 5-15 s. Those tools now run in worker threads, and the radar is cached for 30 s with one
  computation at a time.
- **Throughput is capped by CPU,** not the database: about 160-170 req/s from 2 workers on this machine whatever the
  user count. Extra users mostly add queueing (p50 45 → 166 ms). One app user polling a live chart and the radar
  sends about 0.6 req/s, so this is roughly **250-300 users with a chart open at once per 2 API workers**.
  - Scale by raising `WEB_CONCURRENCY` (about one worker per core) and the host size.
  - Production with 4 cores should handle about twice this.
- **The radar p99 (3 s)** is the request that rebuilds the cache every 30 s.
  - Phase 7 option: have the worker precompute the radar after each candle close, so no request ever rebuilds it.
- **Live candles at scale:** above ~1,000 concurrent chart viewers, push ticks over the existing WebSocket instead
  of 2 s polling. The server already shares one Binance request per series per second.

## Repeat on staging

```bash
# on the staging host, with RATE_LIMIT_ENABLED=false for the duration of the test only
python -m scripts.load_test https://api-staging.example.com --users 50 --duration 120 --json load.json
```

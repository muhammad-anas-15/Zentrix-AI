# Deployment guide

One Docker host per environment (staging, production): Caddy (TLS) → API (several uvicorn workers) + one worker,
PostgreSQL 16, Redis 7, and a nightly backup. Files: `infra/docker-compose.prod.yml`, `infra/Caddyfile`,
`infra/.env.production.example`, `infra/backup/`.

## 1. Choose the host

- **Region:** Binance's public API refuses some regions (for example US addresses). Singapore suits users in
  Pakistan and India, and Binance serves it. Frankfurt also works.
- **Size:**
  - staging: 2 vCPU / 4 GB RAM / 40 GB SSD;
  - production at launch: 4 vCPU / 8 GB.
  - The worker's model inference and the API's analysis tools are CPU-bound.
- **OS:** any Linux with Docker Engine 24+ and the Compose plugin.
- **DNS:** an A (and AAAA) record, e.g. `api-staging.<your domain>`, pointing at the host. Open ports 80 and 443
  only. Use SSH keys and turn password login off.

## 2. First deploy (staging)

```bash
git clone https://github.com/muhammad-anas-15/Zentrix-AI.git && cd Zentrix-AI
git checkout <release tag or commit>
cd infra
cp .env.production.example .env        # fill in every secret; never commit this file
docker compose -f docker-compose.prod.yml --env-file .env build
docker compose -f docker-compose.prod.yml --env-file .env up -d
docker compose -f docker-compose.prod.yml --env-file .env ps   # migrate exited 0; others healthy
```

**Model artifacts:**
- Train them as in `docs/ML_REPORT.md`, or copy `backend/ml/artifacts/`.
- Put them in the `ml_data` volume (`/data/artifacts`).
- Register them once, and again after each retrain:

```bash
docker compose -f docker-compose.prod.yml --env-file .env run --rm worker python -m app.workers.register_models
```

**Admin account:** sign in with Google once in the app, then run:

```bash
docker compose -f docker-compose.prod.yml --env-file .env run --rm api python -m scripts.admin make-admin you@example.com
```

## 3. Check it (acceptance)

Run the smoke test from your machine or CI. It checks:
- liveness and readiness (database and Redis);
- the market and news endpoints;
- security headers;
- that `/docs`, `/openapi.json`, developer sign-in and `/metrics` are not public.

```bash
cd backend && python -m scripts.smoke https://api-staging.example.com
```

Then confirm the worker is ingesting and refreshing news:

```bash
docker compose -f docker-compose.prod.yml logs --since 10m worker | grep -E '"event": "(tick|headlines_refreshed|calendar_refreshed)"'
```

Point a staging build of the app at it (`--dart-define=API_BASE_URL=https://api-staging...`) and sign in with
Google. The staging OAuth client IDs must be in `GOOGLE_CLIENT_IDS`.

## 4. Update and roll back

```bash
git fetch && git checkout <new tag>
IMAGE_TAG=$(git rev-parse --short HEAD) docker compose -f docker-compose.prod.yml --env-file .env up -d --build
python -m scripts.smoke https://api-staging.example.com
```

- **Migrations** run automatically (`migrate` runs before the API and worker start). They are forward-only in
  production: write the next migration rather than downgrading.
- **Rollback:** check out the previous tag and run the same command. If the bad release included a migration,
  first restore the database from the last backup (`docs/RUNBOOK.md`), or ship a fix-forward migration.
- **Order:** staging first, smoke test, then production with the same tag.

## 5. Monitoring

- **Uptime:** an external check on `https://<api>/health` every minute, and `/ready` every 5 minutes
  (for example UptimeRobot or Better Stack).
- **Metrics:** scrape from inside the Docker network:
  - `api:8000/metrics` with `Authorization: Bearer $METRICS_TOKEN`;
  - `worker:9100`.
  - Caddy blocks `/metrics` from the internet.
- **Key series:**

  | Series | Meaning |
  |---|---|
  | `zentrix_http_requests_total{route,status}` | traffic and error rate (alert on 5xx > 1%) |
  | `zentrix_http_request_duration_seconds` | latency by route (alert on p95 > 1 s) |
  | `zentrix_worker_last_tick_timestamp_seconds` | alert if older than 5 minutes |
  | `zentrix_worker_errors_total` | feed, calendar and alert failures |
  | `zentrix_worker_signals_total` | signals created |

- **Errors:** set `SENTRY_DSN` (API and worker) and build the app with its own DSN.
- **Logs:** `docker compose logs`, as JSON lines. Ship them to your log service if you use one.

## 6. Production

Same steps on a second host with `DEPLOY_ENV=prod`, `APP_ENV=prod`, its own domain and its own secrets: never reuse
staging secrets. Before opening it to users, work through:
- `docs/SECURITY.md` open items;
- `docs/PLAY_STORE.md`;
- the data licences in `docs/DATA_SOURCES.md`.

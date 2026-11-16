# Runbook

Commands assume the production stack (`infra/docker-compose.prod.yml`) and are run from `infra/` with
`dc="docker compose -f docker-compose.prod.yml --env-file .env"`.

## Backups

- **What runs:** the `backup` service dumps PostgreSQL every `BACKUP_INTERVAL_S` (default daily) into the `backups`
  volume. It uses custom format, compressed and restorable table by table, and deletes dumps older than
  `BACKUP_KEEP_DAYS` (14). Each run logs `backup_done` with the file and its size, or `backup_failed`.
- **Off-host copy (required):** a backup on the same disk is not a backup. Copy the newest dump off the host at
  least daily. For example, from cron on the host:
  ```bash
  rclone copy /var/lib/docker/volumes/zentrix-prod_backups/_data remote:zentrix-backups --max-age 48h
  ```
- **Dump now:** `$dc exec backup sh /scripts/backup.sh`
- **Redis** holds only caches, rate-limit counters and the worker lock. It is safe to lose (appendonly is on anyway).
- **Model artifacts** (`ml_data` volume) can be rebuilt from the training pipeline. Keep a copy of the registered
  version with the backups.

## Restore

1. Restore into a **new** database (never over the live one):
   ```bash
   $dc exec backup sh /scripts/restore.sh /backups/zentrix-<stamp>.dump zentrix_restore
   ```
   It prints the row counts of users, signals and candles. Compare them with what you expect.
2. To switch over:
   - stop the api and worker (`$dc stop api worker`);
   - rename the databases in psql (`ALTER DATABASE zentrix RENAME TO zentrix_old;` then
     `ALTER DATABASE zentrix_restore RENAME TO zentrix;`);
   - start them again (`$dc up -d api worker`);
   - run the smoke test.
3. Drop `zentrix_old` after a day of normal operation.

**Drill (done 2026-11-16 on the local dev database, same commands):**

| Step | Result |
|---|---|
| Dump | 2.6 MB in 1.0 s |
| Restore into a scratch database | 4.3 s |
| Row counts (12 tables, incl. 111,007 candles, 720 signals, 156 news items) | identical |
| Migration version | `0007` |

Repeat the drill on staging before launch, then every quarter.

## Rotate a secret

| Secret | How | Effect |
|---|---|---|
| `JWT_SECRET` | New value in `.env`, `$dc up -d api` | Every access token is invalid at once; apps refresh (refresh tokens stay valid). |
| `AUDIT_SALT` | New value, restart api | Old audit hashes no longer match new ones (expected). |
| `POSTGRES_PASSWORD` | `ALTER USER zentrix PASSWORD '...'` in psql, then `.env`, then `$dc up -d` | Brief API restart. |
| `TWELVE_DATA_API_KEY` | New key from the Twelve Data dashboard, `.env`, `$dc up -d worker` | None. |
| `METRICS_TOKEN` | New value in `.env` and in the scraper config | — |
| Google OAuth client | Add the new ID to `GOOGLE_CLIENT_IDS` before removing the old one | No sign-in downtime. |
| Android upload key | Ask Play Console support to reset the upload key (Play App Signing keeps the app key) | — |

After any suspected leak: rotate, then revoke all sessions with `UPDATE users SET token_version = token_version + 1;`.

## Incidents

| Symptom | Check | Action |
|---|---|---|
| `/ready` 503 | `$dc ps`, `$dc logs postgres redis` | Restart the failed service; Redis loss is harmless. |
| Worker last tick > 5 min | `$dc logs --since 15m worker` | Feed errors are per series; on `tick_failed` restart the worker. A stuck lock expires after 10 minutes. |
| Twelve Data "budget exhausted" | worker logs | Free plan, 800 calls/day: series resume after 00:00 UTC. Do not add series without a paid plan. |
| Binance 451/403 | worker logs | The host's region is blocked: move the host, or set `BINANCE_SPOT_URL=https://data-api.binance.vision/api/v3/klines`. |
| Many 429s | `zentrix_http_requests_total{status="429"}` | Users behind one carrier IP: raise `RATE_LIMIT_PUBLIC` / `RATE_LIMIT_LIVE`. |
| 5xx spike | Sentry, then `$dc logs api` filtered by `request_id` | Roll back to the previous tag (`docs/DEPLOY.md`). |

Every API error body and log line carries the `request_id`. Ask users for it in support requests.

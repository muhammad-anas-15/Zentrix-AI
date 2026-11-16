# infra/

- **`Dockerfile`:** backend image for the API and the worker. Build with
  `docker build -f infra/Dockerfile backend`. The API runs `WEB_CONCURRENCY` uvicorn workers (default 2), with
  metrics shared through `PROMETHEUS_MULTIPROC_DIR`.
- **`docker-compose.yml`:** local stack (migrate, api, worker, postgres 16, redis 7) bound to localhost.
  Run `docker compose -f infra/docker-compose.yml up --build`.
- **`docker-compose.prod.yml` + `Caddyfile`:** staging and production on one host.
  - Caddy terminates TLS (automatic certificates) and is the only service with public ports.
  - The stack also runs the API, one worker, Postgres, Redis (appendonly) and a nightly `backup` service.
  - Guide: `docs/DEPLOY.md`.
- **`.env.production.example`:** copy it to `infra/.env` on the server, one per environment. Never commit the
  real file.
- **`backup/`:** `backup.sh` (`pg_dump` custom format plus retention), `restore.sh` (into a new database) and the
  loop the backup service runs. Restore and the drill are in `docs/RUNBOOK.md`.
- Model artifacts and the candle cache live in the `ml_data` volume (`/data`), not in the image or git.
- **CI:** `.github/workflows/ci.yml` (lint, types, tests, dependency audit, release builds) and
  `release-android.yml` (signed AAB for Play, from repository secrets).

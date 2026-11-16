# Phase 6: production hardening and release

Branch `phase-6` (from `phase-5.7`). Brief (CLAUDE.md §8):
- security review (OWASP API), secrets management, structured logging, error tracking, metrics, backups;
- CI (lint, tests, build) and a load test on the signal endpoints;
- deployment guide, privacy policy and terms drafts, signed AAB, Play Console checklist.

Accept: a clean staging deploy and a release build.

## Assumptions (defaults; tell me to change any)

1. **Hosting:** any Docker host (a VPS) in a region Binance serves, e.g. Singapore, close to Pakistan and India.
   - Caddy terminates TLS.
   - Staging and production use the same compose file with different `.env` files and domains.
   - The repo cannot pick a provider or domain, so the guide stays provider-neutral.
2. **This machine has no Docker, Redis, Java or Android SDK.** So:
   - The staging deploy is verified as a local production-mode run: `APP_ENV=staging`, JSON logs, several API
     workers, docs off, a smoke test against it. The real server deploy follows `docs/DEPLOY.md`.
   - The signed AAB is built by a GitHub Actions workflow from repository secrets (upload keystore). Locally I build
     the release web app.
3. **Error tracking: Sentry**, optional and off until `SENTRY_DSN` is set, on the API, the worker and the app.
   - No personal data is sent: auth headers, cookies and query strings are stripped.
4. **Metrics:** Prometheus text format.
   - The API serves `/metrics`, behind `METRICS_TOKEN` outside dev.
   - The worker serves its own metrics port.
5. **Legal texts are drafts** for a lawyer to review (Pakistan PECA/PDPB draft, India DPDP Act 2023). Nothing in
   them is legal advice.
6. **Nothing is pushed** until you ask.

## Work

- **Security review (OWASP API Top 10 2023)** → `docs/SECURITY.md`, with each finding fixed or listed. Planned fixes:
  - a JSON 500 handler with a request id, never a stack trace;
  - security headers;
  - a request size limit;
  - API docs off in staging/prod;
  - `Cache-Control: no-store` on authenticated responses.
- **Secrets:** read from files (`SECRETS_DIR`, e.g. Docker secrets at `/run/secrets`) as well as env.
  `.env.production.example` and rotation steps go in the runbook.
- **Logging:** every log line is JSON in staging/prod, including uvicorn and library logs; access logs come from our
  middleware only (path, status, timing, request id; no query strings or tokens).
- **Performance:**
  - CPU-heavy tools (levels base rates, scenario bands, pattern outlook, conditions, radar) run in worker threads, so
    one slow request no longer stalls live polling;
  - several uvicorn workers in the image;
  - a load test script and `docs/LOAD_TEST.md`.
- **Backups:**
  - `pg_dump` scripts with retention, plus a restore script;
  - a restore drill run against the local database, recorded in the runbook.
- **Deploy:**
  - `infra/docker-compose.prod.yml` with Caddy, api, worker, postgres, redis and backup;
  - `docs/DEPLOY.md` covering staging, production, rollback and monitoring;
  - `scripts/smoke.py` for post-deploy checks.
- **CI:** `.github/workflows/ci.yml` covers the backend (ruff, mypy, pytest), the app (analyze, test, release web
  build) and a dependency audit. `release-android.yml` builds a signed AAB from secrets.
- **Android release:**
  - upload-key signing from `key.properties`;
  - R8 shrinking;
  - cleartext HTTP only in debug builds;
  - `https` required and developer sign-in ignored in release builds;
  - privacy and terms links in Settings.
- **Play:** `docs/PLAY_STORE.md` with the store checklist, Data safety answers, financial features declaration,
  reviewer access and listing rules (no binary options).

## Verification

- Full backend and app test suites, including new tests for:
  - 500 handling, headers, size limit and docs toggle;
  - metrics auth;
  - secrets from files;
  - release config guards.
- Local production-mode run (`APP_ENV=staging`, 2+ workers), with a smoke test and a load test against it.
- Backup and restore drill on the dev database.
- Workflow YAML parsed and checked.

## Results (2026-11-16)

- **Tests:**
  - backend 216 passed (10 new: hardening, object access, secrets from files, Sentry scrubbing); ruff and mypy clean;
  - app 64 passed (4 new: release guards, error-report scrubbing, privacy links); analyze clean.
- **Local production-mode run** (`APP_ENV=staging`, 2 uvicorn workers, JSON logs, metrics token):
  - `scripts/smoke.py` 15/15 passed, including docs, openapi, dev sign-in and metrics not public;
  - every log line is JSON, uvicorn's included.
- **Load test:** 158 req/s at 10 users (p50 45 ms, p95 211 ms) and 170 req/s at 50 users (p50 166 ms, p95 881 ms),
  0 errors (`docs/LOAD_TEST.md`).
- **Backup drill:** dump 2.6 MB in 1 s, restore in 4.3 s, all 12 table counts identical (`docs/RUNBOOK.md`).
- **Dependency audit:**
  - the API's dependency tree is clean after raising floors;
  - 3 findings remain in local research-only extras.
- **Release build:** the release web build compiles (as in CI). The signed AAB is built by
  `.github/workflows/release-android.yml`; this machine has no Android SDK or Java.
- **Fixed along the way:**
  - ink ripples were hidden on list rows inside glass cards;
  - a client `X-Request-ID` could inject text into logs;
  - unhandled errors returned plain text;
  - `.env.production.example` was ignored by git.
- **Not done here, needs you:**
  - a server and domain for the real staging deploy;
  - the upload keystore and GitHub secrets;
  - the Play Console account;
  - a lawyer's review of `docs/legal/`;
  - the open items in `docs/SECURITY.md`.

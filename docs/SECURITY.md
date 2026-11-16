# Security review (Phase 6, 2026-11-16)

Scope: the API (`backend/app`), the worker, the deployment files (`infra/`) and the Android app. Method: the OWASP
API Security Top 10 (2023), a code read of every route, tests for each control, and a dependency audit.
**Status:** fixed / in place, or **open** with an owner.

## OWASP API Top 10 (2023)

| # | Risk | Status | Evidence |
|---|---|---|---|
| API1 | Broken object-level authorization | In place | Every user-owned object (journal trade, watchlist, alert, device, inbox event) is loaded through an owner check (`_own`, `own_list`, `user_id ==`). Another user's id returns **404**, so ids cannot be probed. Test: `tests/api/test_object_access.py` sweeps GET/PATCH/DELETE on all of them, plus an alert on someone else's watchlist. |
| API2 | Broken authentication | In place | Google ID tokens are verified (signature by JWKS, `aud`, `iss`, expiry, verified email). Access tokens are short JWTs (HS256; staging/prod refuse a secret under 32 chars). Refresh tokens are stored hashed, rotate on each use, and reuse revokes the family. Logout and logout-all bump `token_version`. Developer sign-in exists only with `APP_ENV=dev/test` + `DEV_LOGIN=true` (settings refuse it elsewhere; test). Sign-in and refresh are rate-limited per IP. |
| API3 | Broken object-property-level authorization | In place | Every input is an explicit Pydantic model: plan, admin flag and entitlements cannot be set through `/v1/me`. Outputs are explicit response models, with no ORM objects serialised wholesale. Admin plan changes are audit-logged. |
| API4 | Unrestricted resource consumption | In place | Per-IP limits on public reads (120/min), live charts (150/min, own bucket), sign-in and refresh; per-user limits (240/min). Page sizes capped (≤ 1000 candles, ≤ 200 signals, ≤ 100 headlines). Per-user caps on alerts, watchlists and items. Request bodies over 64 KiB → 413 (and Caddy caps at 256 KB). CPU-heavy tools run in worker threads and the radar is cached, so one request cannot stall others (Phase 6). **Open:** per-IP limits can bite many users behind one carrier NAT (common in PK/IN). Watch 429 rates in metrics after launch and raise the public limits or add per-device keys. |
| API5 | Broken function-level authorization | In place | Admin API requires `is_admin` (403 otherwise, 401 without a token; test). Admin rights are granted only by the server CLI. Premium gates are enforced server-side when `PREMIUM_ENFORCED=true` (tested both ways). |
| API6 | Unrestricted access to sensitive business flows | Not applicable yet | No payments or rewards. Account creation goes through Google sign-in (rate-limited). |
| API7 | Server-side request forgery | In place | The server fetches only fixed, configured URLs (Binance, Twelve Data, the calendar, the news feeds). No endpoint takes a URL from a user. Feeds have timeouts and size caps (3 MB). |
| API8 | Security misconfiguration | Fixed in Phase 6 | Every response carries: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` and a restrictive CSP. HSTS is sent when deployed. Authenticated responses get `Cache-Control: no-store`. Unhandled errors return a JSON 500 with a request id, never a stack trace (test). `/docs` and `/openapi.json` are off in staging/prod. `/metrics` needs `METRICS_TOKEN` (404 when deployed without one; Caddy blocks it from the internet). CORS is off unless `CORS_ORIGINS` is set. Containers run as a non-root user. Only Caddy publishes ports. |
| API9 | Improper inventory management | In place | One versioned surface (`/v1`). The OpenAPI file is committed and CI fails if it is stale. Dev-only routes are not mounted outside dev. Staging and prod are separate compose projects with separate secrets. |
| API10 | Unsafe consumption of APIs | In place | Third-party data is parsed defensively: RSS/Atom with expat (no external entities, test), size caps, timeouts, http(s) links only, and per-feed failure isolation. Binance and Twelve Data responses are validated into candle frames; a failing feed never blocks others. |

## Other controls

- **Secrets:**
  - Secrets live only in the environment, `backend/.env`, or files under `SECRETS_DIR` (e.g. Docker secrets, one
    file per setting; test).
  - Staging/prod refuse to start without a strong `JWT_SECRET` and `AUDIT_SALT`, and without `GOOGLE_CLIENT_IDS`.
  - A test fails if anything secret-looking is tracked in git.
  - Rotation steps are in `docs/RUNBOOK.md`.
- **Logging:**
  - JSON lines in staging/prod, including uvicorn and library logs.
  - Each request is logged with method, path (no query string), status, duration and request id.
  - Tokens, bodies and headers are never logged.
  - A client-supplied `X-Request-ID` is reused only if it is a plain token, so it cannot inject log lines (test).
- **Error tracking:** Sentry on the API, worker and app, off until a DSN is set. Events drop auth headers, cookies,
  query strings, bodies and the user (tests on both sides). The app sends no screenshots or view hierarchy.
- **Transport:** TLS at Caddy (automatic certificates, HSTS). Release app builds refuse a non-`https` API URL
  (test). Cleartext HTTP is allowed only in debug builds.
- **Mobile:**
  - Tokens are kept in Android encrypted storage (`flutter_secure_storage`), and `allowBackup=false` keeps them off
    cloud backups.
  - Release builds never include developer sign-in (test).
  - Release builds are obfuscated (`--obfuscate`), with symbols kept as a CI artifact.
- **Account deletion:** in-app. It removes the user and their data (cascade) and revokes all tokens; covered since
  Phase 1.
- **Supply chain:**
  - `pip-audit` runs in CI on every push. On 2026-11-16 the API's own dependency tree had 0 known vulnerabilities
    after raising floors (urllib3 ≥ 2.8, certifi ≥ 2026.10.18, pyasn1 ≥ 0.6.5, pip/setuptools in the image).
  - The 3 remaining findings (pillow, filelock, chromadb) are in the local research extras (`[knowledge]`,
    Streamlit). They are not in the API image.
  - **Open:** pin GitHub Actions to commit SHAs before the repository accepts outside contributions.

## Open items (owner: project lead)

1. **Rotate the leaked keys.** The Twelve Data key committed in `41e373e` (and the Gemini key) must be rotated;
   the old values stay in git history.
2. **Data licences before launch:**
   - Twelve Data display licence;
   - Binance written OK for display;
   - a licensed calendar (ForexFactory is unofficial);
   - publisher RSS terms (`docs/DATA_SOURCES.md`).
3. **CGNAT and rate limits:** review after the first week of real traffic (API4).
4. **A penetration test** by a third party before premium billing goes live.

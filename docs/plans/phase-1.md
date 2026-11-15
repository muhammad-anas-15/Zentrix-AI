# Phase 1: backend foundation + auth (with multi-asset schema)

## Goal
FastAPI skeleton on PostgreSQL 16 + Alembic, Google sign-in -> own JWT + rotating refresh tokens, users,
entitlement model, rate limiting, health checks, OpenAPI. Per the expanded scope, the market reference schema
(venues, instruments, listings, timeframes, partitioned candles) is created now so later phases only add tables.
See `docs/ARCHITECTURE.md`.

**Accept:** auth flow works end to end with tests (real Postgres); account deletion works; migrations upgrade
and downgrade cleanly; instruments for all asset classes are queryable.

## Deliverables
1. Settings (env only), structlog JSON logging, consistent error responses, `/v1` API prefix.
2. SQLAlchemy 2 async models + Alembic: `0001` users/auth/entitlements/audit, `0002` market reference + candles
   (monthly partitions) + seed data (FX majors/minors, metals, commodities, Binance spot + perpetuals).
3. Auth: `POST /v1/auth/google`, `/v1/auth/refresh` (rotation, reuse detection revokes the family),
   `/v1/auth/logout`, `/v1/auth/logout-all`; `GET/PATCH /v1/me`; `DELETE /v1/me` (hard delete, audit entry
   without personal data).
4. Rate limiting (Redis fixed window; stricter on auth), `/health` (liveness) and `/ready` (DB + Redis).
5. `GET /v1/instruments` (filters: asset class, type, venue, search), `GET /v1/timeframes`, `GET /v1/venues`.
6. Tests with a real Postgres (bundled via `pgserver`, no Docker needed) and fakeredis; exported OpenAPI.

## Assumptions (defaults; say if you want otherwise)
- Market data only (no trade execution). Crypto spot and perpetuals are separate instruments.
- Access token: HS256 JWT, 15 min. Refresh token: opaque 256-bit, SHA-256 hashed at rest, 30 days, rotated
  on every use. Google ID tokens verified locally against Google's JWKS (cached), `aud` in configured client IDs,
  `email_verified` required.
- Account deletion is a hard delete of the user and all user-owned rows (cascade). `audit_log` keeps
  `account_deleted` with a salted hash of the user id, no email.
- Candles: one table, partitioned monthly by `ts`, double-precision prices. TimescaleDB is not required.
- Seeded listings for feeds we cannot use yet are marked `planned` or `restricted` (for example XAG/USD on the
  Twelve Data free plan) instead of being left out.

## Out of scope (later phases)
Ingestion worker, signals, WebSocket (Phase 2); watchlists, alerts, journal, calculators (Phase 3);
`require_premium` enforcement and admin plan endpoint (Phase 4).

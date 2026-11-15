# Phase 4: premium tiering (no payments)

## Goal
An entitlement layer that billing can plug into later without refactoring. During the build stage every
premium feature stays unlocked for everyone (`PREMIUM_ENFORCED=false`). The API already labels what is Premium,
and it can lock premium features to entitled users by flipping that one setting.

**Accept (CLAUDE.md):** with the flag false, everything is accessible. With it true, premium endpoints refuse free
users. Both are covered by tests. No Play Billing, no paywall, no prices.

## What exists (Phase 1 audit)
- `users.plan` (`free` or `premium`), plus the `subscriptions` and `entitlements` tables. They are not used yet.
- The `PREMIUM_ENFORCED` setting (default false). `/v1/me` reports `premium_access`, but it only looks at `users.plan`.
- `ScenarioOut.premium: bool`. No route checks anything.

## Deliverables
1. **Feature registry** (`app/services/entitlements.py`): one table of every product feature with its tier
   (free or premium), title and description. The gates, the badges, `/v1/plans` and the docs are all derived
   from it.
2. **Access resolution:** `resolve_access(db, user, now)`. A user has Premium when any one of these holds:
   - `users.plan = premium` and `plan_expires_at` is empty or in the future;
   - a subscription is `active` or `grace` and has not expired (billing writes these rows later);
   - an `entitlements` row with key `premium` is active now (an admin or promo grant).
   A grant whose key is a single feature unlocks only that feature, for example a trial of the scenario path.
3. **Gates:**
   - `require_premium(feature)` is a dependency for whole premium endpoints.
   - `Gate.allows(feature)` and `Gate.require(feature)` handle endpoints that are only partly premium.
   - With the flag false, the gate never queries the database and lets everyone through, including anonymous
     callers.
   - With the flag true, an anonymous caller gets 401 and a user without access gets
     `403 premium_required {feature}`.
4. **Labels in responses:**
   - Responses of premium features carry `premium: {"feature": ..., "label": "Premium"}`.
   - Free responses that had a premium part withheld carry `premium_locked: [feature, ...]`.
   - OpenAPI marks each gated operation with `x-premium` (feature and scope), and its summary ends with
     "(Premium)".
5. **Public catalogue `GET /v1/plans`:** features by tier, the free markets, `enforced`, and a note that billing
   does not exist yet. **`GET /v1/me/access`** returns the caller's effective plan, where it comes from, its
   expiry, and per-feature availability. `/v1/me` `premium_access` and `plan` use the same resolution.
6. **Admin:**
   - Migration 0005 adds `users.is_admin`, `users.plan_expires_at`, and `entitlements.note`, `granted_by` and
     `created_at`.
   - Endpoints under `/v1/admin`:
     - user search and detail;
     - `PUT /users/{id}/plan` with plan, optional expiry and a required reason;
     - grant and end entitlements.
   - Every change is written to `audit_log`, with the acting admin and the reason.
   - Admin rights are set only from the server CLI (`python -m scripts.admin`), never through the API, so the
     API offers no path to privilege escalation.
7. **Worker:** while enforcement is on, signal alerts do not fire for users without `signal_alerts`.
8. **Docs:** an API.md section, ARCHITECTURE, README (admin CLI), `.env.example` and OpenAPI 0.5.0.

## Feature tiers (from CLAUDE.md section 7)

| Feature key | Tier | Gate while enforced |
|---|---|---|
| `market_conditions`, `news_guard`, `position_size`, `track_record`, `watchlists`, `price_alerts`, `risk_profile`, `free_signals` | free | none |
| `all_markets` | premium | Live signals outside the free markets, which default to EUR/USD, GBP/USD and XAU/USD on 15m. `GET /v1/signals/latest` returns 403 for other markets. The signal history, WebSocket signal events and watchlist quotes withhold *unresolved* signals of other markets. |
| `signal_alerts` | premium | Creating or resuming a `signal` alert; the worker skips users without access |
| `trade_levels` | premium | `GET /v1/levels`, `GET /v1/signals/{id}/levels` |
| `exit_advisor` | premium | `POST /v1/exit-advice` |
| `scenario` | premium | `GET /v1/scenario` |
| `journal` | premium | Adding or editing trades, stats, review |
| `risk_guard` | premium | `GET /v1/me/risk-status`; the daily-loss check inside the position-size calculator |

## Assumptions (defaults; say if you want otherwise)
- **Your data is never locked.** Even while enforced, a user can always list, read, pause and delete what they
  saved (journal trades, signal alerts) and delete the account. Only creating new premium data and the analytics
  are gated.
- **The public track record stays complete and honest.** Every signal appears with its outcome. While
  enforcement is on, only the *live* (still unresolved) signals of premium markets are hidden from free viewers,
  until they resolve. The accuracy stats (`/v1/track-record`) are never filtered.
- **The free-tier daily cap** ("2-3 signals/day") is not built. CLAUDE.md says free-tier limits are not enforced
  yet, and how to count them is a product decision. The free-market list is the part that is built, and it is
  configurable (`FREE_SIGNAL_SYMBOLS`, `FREE_SIGNAL_TIMEFRAMES`).
- **Admins are identified by `users.is_admin`.** It is bootstrapped by CLI on the server. Admins cannot grant
  admin rights through the API. A non-admin gets 403 `forbidden`.
- **Plan expiry is lazy.** An expired plan simply stops counting at request time, so no job is needed.
  Setting the plan to `free` clears the expiry.
- **The WebSocket** accepts an optional `{"action": "auth", "access_token": ...}` message. It is needed only to
  receive premium-market signal events while enforced. Candle events stay public. Access is checked when the
  client authenticates, and stops when the token expires.
- **"Full English/Urdu explanation"** is premium in CLAUDE.md, but there is no explanation endpoint yet. Its gate
  will be added together with the endpoint, in Phase 5 or 6.
- The API version becomes 0.5.0.

## Tests
- Flag false: every premium endpoint works for anonymous callers and free users, with labels present.
- Flag true:
  - Each gated endpoint returns 401 to anonymous callers and 403 `premium_required` to free users.
  - It allows: the premium plan; an active `premium` grant; a single-feature grant (that feature only); an active
    subscription.
  - It refuses: an expired plan, an ended grant, a cancelled subscription.
  - The partly-premium paths: signal history and latest signal, watchlist quotes, the daily-loss check in position
    size, creating and resuming a signal alert, worker signal alerts, WebSocket signal events.
  - Your data stays readable and deletable.
- Registry and OpenAPI consistency: every gated route is marked in OpenAPI and documented in API.md, and every
  marked route is gated.
- Admin:
  - Non-admins are refused.
  - Search and detail work.
  - Setting a plan changes `/v1/me`, writes the audit log and rejects a past expiry.
  - Granting and ending an entitlement work.
  - The CLI can make an admin.
  - Account deletion removes entitlements and keeps the admin's audit rows.

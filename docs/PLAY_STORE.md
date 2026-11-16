# Google Play release checklist

The app is positioned as **analysis and risk tools for forex, gold and crypto**. It is not a broker, does not place
trades, and holds no money. Do not mention Quotex, binary options or fixed-expiry trades anywhere: listing,
screenshots, or replies to reviews (CLAUDE.md §9).

## 1. Before the first upload

- [ ] **Play Console developer account.**
  - A personal account created after Nov 2023 must run a **closed test with at least 12 testers for 14 days**
    before it can publish to production. Plan for it.
  - An organisation account (D-U-N-S number) skips that.
- [ ] **Confirm the application id `ai.zentrix.app`.** It can never change after the first upload.
- [ ] **Upload key.** Create it once, keep two offline copies, and never commit it:
  ```bash
  keytool -genkeypair -v -keystore upload-keystore.jks -alias upload -keyalg RSA -keysize 4096 -validity 10000
  base64 -w0 upload-keystore.jks   # -> GitHub secret ANDROID_KEYSTORE_BASE64
  ```
  - GitHub repository secrets (Settings → Secrets → Actions, or a `release` environment with required reviewers):
    `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`, and
    optionally `SENTRY_DSN`.
- [ ] **Play App Signing:** accept it at the first upload. Google keeps the app signing key and you keep only the
  upload key.
- [ ] **Google sign-in:**
  - In Google Cloud, create an **Android OAuth client** for `ai.zentrix.app` with the SHA-1 of both the upload key
    and the Play app signing key (Play Console → Setup → App signing).
  - The **web client ID** goes into `GOOGLE_SERVER_CLIENT_ID` (app) and `GOOGLE_CLIENT_IDS` (API).
- [ ] **A production API is running** and passes `scripts/smoke.py` (`docs/DEPLOY.md`).
- [ ] **Privacy policy and terms are published at public https URLs.** Drafts are in `docs/legal/` and must be
  reviewed by a lawyer first.

## 2. Build the bundle

1. GitHub → Actions → **Android release** → Run workflow.
2. Enter:
   - the API URL (`https://...`);
   - the Google web client ID;
   - the privacy and terms URLs;
   - the version name. The build number is the run number, so it always increases.
3. Download the artifact. It contains `app-release.aab` plus the obfuscation symbols; keep the symbols to read
   crash stack traces.

Release builds refuse an `http://` API URL and never contain developer sign-in.

## 3. Store listing

- **Name:** Zentrix
- **Short description** (≤ 80 chars), e.g. "Forex, gold & crypto market conditions, risk calculator and news pulse".
- **Full description:** what it does (Market Radar, live charts, risk calculator, journal, news and calendar,
  public track record). Include "Not financial advice. Signals are probabilities based on past data, not
  guarantees." No profit claims, no accuracy numbers that are not the live track record.
- **Category:** Finance. Add a contact email and the privacy policy URL.
- **Screenshots:** phone, at least 2 (use the Radar, a chart, the calculator and the Pulse).
  - Show the disclaimer where visible.
  - Never show expiry times or "next candle" calls.

## 4. App content (Policy → App content)

| Declaration | Answer |
|---|---|
| Privacy policy | The published URL |
| Ads | No ads |
| App access | Most features work without an account ("Explore without an account"). Journal and alerts need Google sign-in; give reviewers a test Google account if asked. |
| Content rating | Questionnaire: reference/news/education-like utility, no user interaction between users, no gambling. Expect "Everyone"/"3+", but set the **target audience to 18+**. |
| Target audience | 18 and over |
| News app | No (news is one section, not the main purpose) |
| **Financial features** | The app shows market data, analysis and risk tools. It does **not** offer trading, brokerage, payments, loans, a crypto exchange or a wallet. Answer accordingly and describe it that way in the declaration. |
| Government app | No |
| Data safety | See section 5 |
| Account deletion | In app: Settings → Delete account. Also give a **web URL** where users can request deletion without the app (a page or form linked from the privacy policy). Play requires both. |

## 5. Data safety form

| Data type | Collected | Shared | Purpose | Optional? |
|---|---|---|---|---|
| Name, email (from Google sign-in) | Yes | No | Account management | Yes (guest mode) |
| User-generated content: journal trades and notes, watchlists, alerts | Yes | No | App functionality | Yes |
| Device or other IDs: Firebase push token | Yes, when push is enabled | No | App functionality (alerts) | Yes |
| App info and performance: crash logs, diagnostics | Only in builds with `SENTRY_DSN` | No (Sentry is a service provider) | App functionality / diagnostics | No |
| Approximate location, contacts, photos, financial account info | No | — | — | — |

Also declare:
- data is **encrypted in transit** (HTTPS only);
- users **can request deletion** (in app and by the web URL);
- IP addresses are processed transiently for rate limiting and abuse protection.

Hosting, Sentry and Google/Firebase act as service providers, which Play does not count as "sharing".

## 6. Release tracks

1. **Internal testing:** you and the team, with the staging API. Check sign-in, deletion, push and Urdu.
2. **Closed testing:** at least 12 testers for 14 days (personal accounts). Fix pre-launch report issues
   (Play Console runs the app on test devices).
3. **Production:** staged rollout of 10% → 50% → 100%. Watch Sentry and `/metrics` between steps.

## 7. Regulatory notes (flag, don't hide)

- **India:** SEBI regulates investment advisers and research analysts.
  - Keep the app descriptive (conditions, ranges, base rates, history); signals stay "Very Weak - Wait" until a
    strength tier is proven, and are labelled as probabilities.
  - Have a lawyer confirm before marketing signals as a paid feature.
  - Crypto income is taxed and offshore-exchange access is restricted; the app shows public market data only.
- **Pakistan:** forex and crypto promotion faces SECP and State Bank scrutiny. Same positioning, with legal review
  before paid features.
- **Everywhere:** no binary options, no "guaranteed" language, and the disclaimer on every screen with
  signals or projections (already in the app).

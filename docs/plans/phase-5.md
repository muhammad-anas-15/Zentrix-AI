# Phase 5: Flutter app

## Goal
The Android app (Flutter), built on the finished backend (Phases 0-4). It covers sign-in, the dashboard, the pair
view with candles and a signal card, the risk calculator, the journal, the track record, alerts, settings and
account deletion, in English and Urdu (RTL).

Premium features show a "Premium" badge. They are never locked by the app and there is no paywall. If the server
enforces premium, the app shows a plain "not on your plan" state with nothing to buy.

**Accept (CLAUDE.md):** it runs on a real Android device against the local backend. This machine has Flutter
3.44.8 and Chrome but no Android SDK or Java. Here I verify with `flutter analyze`, unit and widget tests, and a web
build driven in Chrome against the local backend. The real-device run is a documented step for you
(`mobile/README.md`).

## Stack
Flutter stable (3.44, Dart 3.12):

| Area | Packages |
|---|---|
| State | flutter_riverpod (no codegen) |
| Navigation | go_router (auth redirect, bottom-navigation shell) |
| Networking | dio, with a queued refresh interceptor. The refresh token is single-use, so concurrent 401s refresh once |
| Models | freezed + json_serializable (snake_case set once in `build.yaml`) |
| Storage | flutter_secure_storage (tokens), shared_preferences (theme, language) |
| Sign-in | google_sign_in |
| Language | flutter_localizations + gen-l10n (ARB) |

Charts: a custom `CustomPainter` candlestick chart (pan, pinch-zoom, crosshair, last-price line). It avoids a
licence or a heavy dependency, and its colours come from the design tokens.

## Design tokens (non-negotiable)
- **One token layer:** `lib/core/theme/tokens.dart` holds the palette (dark and light), spacing, radii, type
  scale, elevation/blur and durations. `lib/core/theme/theme.dart` builds `ThemeData` plus a `ZxTheme`
  `ThemeExtension` from it.
- **Screens read only tokens:** they use `context.zx` (semantic colours and text styles) and the `ZxSpace` /
  `ZxRadius` constants. A test fails if a raw `Color(...)`, a `Colors.*` colour or a literal `fontSize` appears
  outside `lib/core/theme/`.
- **Look:** dark mode first.
  - Background: obsidian/charcoal.
  - Cards: translucent "glass" with a subtle border.
  - Signals: emerald for bullish or success, coral/crimson for bearish or danger, amber for caution.
  - Accents: violet/indigo for primary actions, gold for the Premium badge.
  - Prices: tabular figures.
- **Light theme:** from the same tokens, with a theme toggle (system / dark / light).
- **No new branding:** no logo or mascot; the name is set in plain type. The tokens are where the Claude Design
  output will plug in later.

## Honesty in the UI
- **Signal strength:** shown exactly as the server sends it. "Very Weak - Wait" is a neutral grey badge, never green
  or red.
- **No demonstrated edge:** when a model has none, the card says so and treats the direction as 50/50.
- **Accuracy figures:** only the live track record, plus backtest numbers labelled "backtest". The app never
  computes or claims a figure of its own.
- **Disclaimer:** "Not financial advice" appears on the signal card, tool results and the track record.

## Structure (`mobile/`)
```
lib/
  main.dart, app.dart                 bootstrap, MaterialApp.router, themes, locale
  core/
    config/app_config.dart            API_BASE_URL, GOOGLE_SERVER_CLIENT_ID, DEV_LOGIN (--dart-define)
    theme/tokens.dart, theme.dart     design tokens -> ThemeData + ZxTheme extension
    network/api_client.dart           dio, auth + refresh interceptor, error mapping (ApiException)
    storage/token_store.dart          secure token storage
    format/formatters.dart            prices, percents, countdowns, dates (locale-aware)
    router/router.dart                routes, auth redirect, shell
    widgets/                          GlassCard, PremiumBadge, StrengthBadge, ConditionLight, MetricTile,
                                      AsyncValueView (loading/error/empty), Disclaimer, PremiumLockedCard
  l10n/app_en.arb, app_ur.arb         all user-facing strings (generated AppLocalizations)
  features/
    auth/          session controller (tokens, current user, access), splash, sign-in
    dashboard/     condition light, news countdown, ticker strip, quick watchlist
    market/        instruments list, pair view: candle chart, signal card, ATR levels, conditions
    risk/          position-size calculator
    journal/       trades list, add/close trade, stats (Premium)
    track_record/  live stats by strength, recent signals with outcomes
    alerts/        alerts list and create (price / % / news / signal), inbox
    settings/      profile, language, theme, plan and access, sign out (here / everywhere), delete account
test/                                 unit + widget tests (fake repositories), token hygiene test
```

## Backend additions
- **Developer sign-in** (`POST /v1/auth/dev`) lets the app be exercised before the Google OAuth client IDs exist.
  It is mounted only when `APP_ENV=dev` and `DEV_LOGIN=true`; the settings refuse `DEV_LOGIN` anywhere else. It
  issues the normal token pair for a `dev` identity and is covered by tests. The app shows the button only when
  built with `--dart-define=DEV_LOGIN=true`.
- **No new data endpoints.** Guests read the public endpoints; the dashboard ticker for guests uses
  `/v1/candles`.

## Assumptions (defaults; say if you want otherwise)
- **App id `ai.zentrix.app`:** this is the Android application id, which cannot be changed after the first Play
  upload. Confirm it before release.
- **Guest mode:** "Explore without an account" opens the public features (conditions, chart, signals, calculator,
  track record). The journal, watchlists, alerts and settings need sign-in.
- **Push:** FCM registration is behind an interface with a no-op implementation until the Firebase project and
  `google-services.json` exist. The in-app alert inbox works without it.
- **Fonts:** the platform font (Roboto on Android) with tabular figures. The font family is a token, so a bundled
  font, for example an Urdu Nastaliq face, is a one-line change later.
- **Urdu:** my Urdu strings need review by a native speaker before release.
- **Not in this phase:** Play Billing or any paywall, iOS polish, and offline caching.

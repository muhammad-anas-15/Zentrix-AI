# Zentrix app (Flutter)

Android-first Flutter app for the Zentrix API. It covers:
- sign-in, plus a guest mode;
- the dashboard (condition light, news guard, latest signal, quick watchlist);
- markets and the pair view (candlestick chart, signal card, ATR levels);
- the position-size calculator;
- the journal and stats;
- the public track record;
- alerts;
- settings, including in-app account deletion.

Languages are English and Urdu, laid out right-to-left. **Not financial advice.**

## Stack

| Area | Packages |
|---|---|
| State | flutter_riverpod 3 (no codegen) |
| Navigation | go_router (auth redirects, 5-tab shell) |
| Networking | dio. One queued interceptor refreshes the token once for a burst of 401s, because the backend's refresh tokens are single-use |
| Models | freezed + json_serializable (`build.yaml` sets snake_case once) |
| Storage | flutter_secure_storage (tokens), shared_preferences (theme, language) |
| Sign-in | google_sign_in 7 |
| Language | flutter_localizations + gen-l10n (`lib/l10n/*.arb`) |

The candlestick chart is a `CustomPainter` (`lib/features/market/presentation/widgets/candle_chart.dart`): drag to
pan, pinch to zoom, long-press for the crosshair.

## Design tokens

- Every colour, spacing, radius, type size and duration lives in `lib/core/theme/tokens.dart`. `theme.dart` builds
  `ThemeData` and the `ZxTheme` extension from it.
- Widgets read only `context.zx` (`palette`, `text`) and the `ZxSpace` / `ZxRadius` / `ZxSize` constants. To restyle
  the app, change the tokens.
- `test/core/design_tokens_test.dart` enforces this:
  - it fails on a raw `Color(0x…)`, a `Colors.*` colour or a literal `fontSize:` outside `lib/core/theme/`;
  - it checks WCAG contrast for both palettes.
- Dark is the default. A light theme is built from the same tokens, and Settings switches between system, dark and
  light.

## Honesty rules in the UI

- Signal strength is shown exactly as the server sends it. "Very Weak - Wait" is a neutral grey badge.
- When the model has no demonstrated edge, the direction is greyed out and the card says to treat it as 50/50.
- The only accuracy numbers shown are:
  - the live track record;
  - backtest numbers, labelled "backtest";
  - the historical base rates of the ATR levels, each next to its break-even rate.
- If the news calendar is stale, the news guard says the news risk is unknown. It never says "no events".
- "Premium" is a label only. If the server enforces premium (`403 premium_required`), the app shows a plain "not on
  your plan" card with nothing to buy.

## Setup

```bash
cd mobile
flutter pub get
dart run build_runner build --delete-conflicting-outputs   # freezed / json models (*.g.dart, *.freezed.dart)
flutter analyze
flutter test
```

Generated code is not committed. `flutter gen-l10n` runs automatically on `pub get`, `run`, `test` and `build`.

**Windows: paths with spaces.** If the Flutter SDK or your user folder has a space in its path (for example
`C:\Users\First Last`), `flutter test` and `build` fail with `'C:\Users\First' is not recognized` while compiling a
native-assets hook. Install Flutter in a folder without spaces, for example `C:\src\flutter`, and set `PUB_CACHE` to
one too (for example `C:\pub-cache`). Alternatively, call Flutter through the 8.3 short path
(`C:\Users\FIRST~1\...\flutter\bin\flutter`) and point `PUB_CACHE` at the short path of
`%LOCALAPPDATA%\Pub\Cache`.

## Run against the local backend

Start the backend (`../README.md`) with developer sign-in. The app can then be used before the Google OAuth client
IDs exist:

```bash
cd backend
APP_ENV=dev DEV_LOGIN=true uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Android emulator.** The default API URL is `http://10.0.2.2:8000`, the host machine as seen from the emulator.

```bash
flutter run --dart-define=DEV_LOGIN=true
```

**Real Android device** (USB debugging on). There are two ways:

```bash
# simplest: forward the phone's port 8000 to the PC
adb reverse tcp:8000 tcp:8000
flutter run --dart-define=API_BASE_URL=http://127.0.0.1:8000 --dart-define=DEV_LOGIN=true

# or over Wi-Fi: same network, allow port 8000 in the PC firewall
flutter run --dart-define=API_BASE_URL=http://192.168.x.y:8000 --dart-define=DEV_LOGIN=true
```

Debug builds allow plain HTTP (`android/app/src/debug/AndroidManifest.xml`). Release builds are HTTPS only.

**Web (development checks only).** Start the backend with `CORS_ORIGINS=http://127.0.0.1:8090` as well, then:

```bash
flutter build web --no-web-resources-cdn --dart-define=API_BASE_URL=http://127.0.0.1:8000 --dart-define=DEV_LOGIN=true
python -m http.server 8090 --directory build/web
```

## Build-time settings (`--dart-define`)

| Key | Default | Purpose |
|---|---|---|
| `API_BASE_URL` | `http://10.0.2.2:8000` (web: `http://127.0.0.1:8000`) | Backend base URL |
| `GOOGLE_SERVER_CLIENT_ID` | empty | OAuth **web** client ID. It is the audience of the ID token, and must be listed in the backend's `GOOGLE_CLIENT_IDS`. While empty, the Google button is disabled |
| `GOOGLE_CLIENT_ID` | empty | iOS client ID (not needed on Android) |
| `DEV_LOGIN` | false | Shows "Developer sign-in". It works only against a backend with `APP_ENV=dev` and `DEV_LOGIN=true` |
| `DEV_AUTO_SIGN_IN` | empty | Developer builds only: signs in as this email at start-up (for demos and screenshots) |

The app contains no secrets. The Google client IDs are public identifiers.

## Google sign-in (when the OAuth client IDs exist)

1. In Google Cloud (OAuth consent screen configured), create an **Android** OAuth client:
   - package `ai.zentrix.app`;
   - SHA-1 from `keytool -list -v -keystore ~/.android/debug.keystore` (later also the upload/Play signing key).
2. Create a **Web** OAuth client. Its ID is the server client ID.
3. Backend: `GOOGLE_CLIENT_IDS=<web client id>` (plus the iOS ID later).
4. App: `flutter run --dart-define=GOOGLE_SERVER_CLIENT_ID=<web client id> --dart-define=API_BASE_URL=...`

## Structure

```
lib/
  main.dart, app.dart                 bootstrap, MaterialApp.router, theme mode, locale
  core/  config/ theme/ network/ storage/ format/ router/ widgets/ l10n.dart providers.dart
  l10n/  app_en.arb, app_ur.arb       (generated: lib/l10n/gen/)
  features/<feature>/{domain,data,application,presentation}
    auth  dashboard  market  risk  journal  track_record  alerts  settings
test/    tokens, formatters, API client (refresh), models, session/router, widgets
```

## Not done yet

- **Push notifications:** these need a Firebase project and `android/app/google-services.json`. Until then, alerts
  show in the in-app inbox.
- **Release signing:** the upload keystore and a signed AAB come in Phase 6. The application id `ai.zentrix.app`
  cannot change after the first Play upload, so confirm it before release.
- **Urdu text:** the strings need a review by a native speaker. Server-generated details (condition reasons, warnings)
  are still in English.
- **Fonts:** the app uses the platform font, with tabular figures for prices. A bundled font, for example a Nastaliq
  face for Urdu, is a one-line change in `tokens.dart`.
- **Visual design:** from Claude Design later. It applies through the tokens.

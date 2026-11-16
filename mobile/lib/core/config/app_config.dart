import 'package:flutter/foundation.dart';

/// Build-time configuration (`--dart-define=KEY=value`). No secrets live in the app.
@immutable
class AppConfig {
  const AppConfig({
    required this.apiBaseUrl,
    this.googleServerClientId = '',
    this.googleClientId = '',
    this.devLogin = false,
    this.devAutoSignIn = '',
    this.sentryDsn = '',
    this.privacyUrl = '',
    this.termsUrl = '',
    this.environment = 'dev',
  });

  /// From `--dart-define`s. The default API is the host machine as seen from the Android emulator
  /// (10.0.2.2) or from a browser (127.0.0.1), port 8000. Release builds are checked by [forBuild].
  factory AppConfig.fromEnvironment() => AppConfig.forBuild(
    release: kReleaseMode,
    web: kIsWeb,
    apiBaseUrl: const String.fromEnvironment('API_BASE_URL'),
    googleServerClientId: const String.fromEnvironment('GOOGLE_SERVER_CLIENT_ID'),
    googleClientId: const String.fromEnvironment('GOOGLE_CLIENT_ID'),
    devLogin: const bool.fromEnvironment('DEV_LOGIN'),
    devAutoSignIn: const String.fromEnvironment('DEV_AUTO_SIGN_IN'),
    sentryDsn: const String.fromEnvironment('SENTRY_DSN'),
    privacyUrl: const String.fromEnvironment('PRIVACY_URL'),
    termsUrl: const String.fromEnvironment('TERMS_URL'),
    environment: const String.fromEnvironment('APP_ENV'),
  );

  /// The configuration of a build. A release build must talk to the API over HTTPS and never offers the developer
  /// sign-in, whatever was passed (so a store build cannot ship with it by mistake).
  factory AppConfig.forBuild({
    required bool release,
    required bool web,
    String apiBaseUrl = '',
    String googleServerClientId = '',
    String googleClientId = '',
    bool devLogin = false,
    String devAutoSignIn = '',
    String sentryDsn = '',
    String privacyUrl = '',
    String termsUrl = '',
    String environment = '',
  }) {
    if (release) {
      final uri = Uri.tryParse(apiBaseUrl);
      if (uri == null || uri.scheme != 'https' || uri.host.isEmpty) {
        throw StateError('Release builds need --dart-define=API_BASE_URL=https://... (got "$apiBaseUrl")');
      }
    }
    return AppConfig(
      apiBaseUrl: apiBaseUrl.isNotEmpty ? apiBaseUrl : (web ? 'http://127.0.0.1:8000' : 'http://10.0.2.2:8000'),
      googleServerClientId: googleServerClientId,
      googleClientId: googleClientId,
      devLogin: devLogin && !release,
      devAutoSignIn: release ? '' : devAutoSignIn,
      sentryDsn: sentryDsn,
      privacyUrl: privacyUrl,
      termsUrl: termsUrl,
      environment: environment.isNotEmpty ? environment : (release ? 'prod' : 'dev'),
    );
  }

  final String apiBaseUrl;

  /// OAuth "web" client ID: the audience of the Google ID token the backend verifies (GOOGLE_CLIENT_IDS).
  final String googleServerClientId;

  /// Platform client ID (iOS / web); Android uses the package name + SHA-1 registered in Google Cloud.
  final String googleClientId;

  /// Show the developer sign-in (backend `POST /v1/auth/dev`, only with APP_ENV=dev and DEV_LOGIN=true).
  final bool devLogin;

  /// Developer builds only: sign in as this email at start-up (demos, screenshots). Ignored without [devLogin].
  final String devAutoSignIn;

  /// Sentry crash and error reporting; empty = off. No personal data is sent.
  final String sentryDsn;

  /// Public privacy policy and terms pages (shown in Settings; required by Google Play).
  final String privacyUrl;
  final String termsUrl;

  /// dev | staging | prod: tags error reports.
  final String environment;

  bool get googleConfigured => googleServerClientId.isNotEmpty;
}

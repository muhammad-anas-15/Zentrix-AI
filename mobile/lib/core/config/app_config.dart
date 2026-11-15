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
  });

  /// From `--dart-define`s. The default API is the host machine as seen from the Android emulator
  /// (10.0.2.2) or from a browser (127.0.0.1), port 8000.
  factory AppConfig.fromEnvironment() {
    const url = String.fromEnvironment('API_BASE_URL');
    return AppConfig(
      apiBaseUrl: url.isNotEmpty ? url : (kIsWeb ? 'http://127.0.0.1:8000' : 'http://10.0.2.2:8000'),
      googleServerClientId: const String.fromEnvironment('GOOGLE_SERVER_CLIENT_ID'),
      googleClientId: const String.fromEnvironment('GOOGLE_CLIENT_ID'),
      devLogin: const bool.fromEnvironment('DEV_LOGIN'),
      devAutoSignIn: const String.fromEnvironment('DEV_AUTO_SIGN_IN'),
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

  bool get googleConfigured => googleServerClientId.isNotEmpty;
}

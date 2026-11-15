import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:google_sign_in/google_sign_in.dart';

import '../../../core/config/app_config.dart';
import '../../../core/network/api_client.dart';
import '../../../core/providers.dart';
import '../domain/models.dart';

Map<String, dynamic> _map(Object? json) => json! as Map<String, dynamic>;

/// Sessions and the account (`/v1/auth/*`, `/v1/me`).
class AuthRepository {
  AuthRepository(this._api);

  final ApiClient _api;

  Future<TokenResponse> signInWithGoogle(String idToken, {String? deviceName}) => _api.post(
    '/v1/auth/google',
    (j) => TokenResponse.fromJson(_map(j)),
    body: <String, Object?>{'id_token': idToken, 'device_name': deviceName},
    auth: false,
  );

  /// Developer sign-in (backend APP_ENV=dev and DEV_LOGIN=true only).
  Future<TokenResponse> signInDev(String email) => _api.post(
    '/v1/auth/dev',
    (j) => TokenResponse.fromJson(_map(j)),
    body: <String, Object?>{'email': email, 'device_name': 'zentrix-app'},
    auth: false,
  );

  Future<AppUser> me() => _api.get('/v1/me', (j) => AppUser.fromJson(_map(j)));

  Future<AppUser> updateMe({String? locale, String? displayName, String? timezone}) => _api.patch(
    '/v1/me',
    (j) => AppUser.fromJson(_map(j)),
    body: <String, Object?>{'locale': ?locale, 'display_name': ?displayName, 'timezone': ?timezone},
  );

  Future<Access> access() => _api.get('/v1/me/access', (j) => Access.fromJson(_map(j)));

  Future<void> logout(String refreshToken) =>
      _api.post('/v1/auth/logout', (_) {}, body: <String, String>{'refresh_token': refreshToken}, auth: false);

  Future<void> logoutAll() => _api.post('/v1/auth/logout-all', (_) {});

  Future<void> deleteAccount() => _api.delete('/v1/me');
}

final authRepositoryProvider = Provider<AuthRepository>((ref) => AuthRepository(ref.watch(apiClientProvider)));

/// Google sign-in, behind an interface so tests and builds without client IDs do not touch the plugin.
abstract interface class GoogleAuthGateway {
  /// True when this build has the OAuth client IDs and the platform supports the native flow.
  bool get available;

  /// Google ID token for the backend (audience = the server client ID).
  Future<String> idToken();

  Future<void> signOut();
}

class PluginGoogleAuth implements GoogleAuthGateway {
  PluginGoogleAuth(this._config);

  final AppConfig _config;
  Future<void>? _init;

  @override
  bool get available => _config.googleConfigured && GoogleSignIn.instance.supportsAuthenticate();

  Future<void> _ensureInit() => _init ??= GoogleSignIn.instance.initialize(
    clientId: _config.googleClientId.isEmpty ? null : _config.googleClientId,
    serverClientId: _config.googleServerClientId,
  );

  @override
  Future<String> idToken() async {
    await _ensureInit();
    final account = await GoogleSignIn.instance.authenticate();
    final token = account.authentication.idToken;
    if (token == null) throw StateError('Google returned no ID token');
    return token;
  }

  @override
  Future<void> signOut() async {
    if (!available) return;
    await _ensureInit();
    await GoogleSignIn.instance.signOut();
  }
}

final googleAuthProvider = Provider<GoogleAuthGateway>((ref) => PluginGoogleAuth(ref.watch(appConfigProvider)));

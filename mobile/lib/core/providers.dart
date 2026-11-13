import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'config/app_config.dart';
import 'network/api_client.dart';
import 'storage/token_store.dart';

/// Build-time configuration (overridden in tests).
final appConfigProvider = Provider<AppConfig>((ref) => AppConfig.fromEnvironment());

final tokenStoreProvider = Provider<TokenStore>((ref) => SecureTokenStore());

/// Set in main() after SharedPreferences.getInstance().
final sharedPreferencesProvider = Provider<SharedPreferences>(
  (ref) => throw UnimplementedError('override sharedPreferencesProvider'),
);

final apiClientProvider = Provider<ApiClient>((ref) {
  final client = ApiClient(baseUrl: ref.watch(appConfigProvider).apiBaseUrl, tokens: ref.watch(tokenStoreProvider));
  ref.onDispose(client.close);
  return client;
});

/// A tick every second, for countdowns.
final secondTickerProvider = StreamProvider.autoDispose<DateTime>(
  (ref) => Stream<DateTime>.periodic(const Duration(seconds: 1), (_) => DateTime.now()),
);

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'app.dart';
import 'core/config/app_config.dart';
import 'core/providers.dart';
import 'core/telemetry.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  LicenseRegistry.addLicense(_fontLicenses);
  // Fails fast on a misconfigured release build (e.g. an http:// API URL) instead of shipping it.
  final config = AppConfig.fromEnvironment();
  final prefs = await SharedPreferences.getInstance();
  await runWithTelemetry(
    config,
    () => runApp(
      ProviderScope(
        overrides: [sharedPreferencesProvider.overrideWithValue(prefs), appConfigProvider.overrideWithValue(config)],
        // No blind retries: the API client already refreshes tokens; the UI offers "Retry".
        retry: (retryCount, error) => null,
        child: const ZentrixApp(),
      ),
    ),
  );
}

/// The bundled fonts' SIL OFL licences, listed on the app's licence page.
Stream<LicenseEntry> _fontLicenses() async* {
  for (final (pkg, file) in [
    ('Inter', 'Inter-OFL.txt'),
    ('JetBrains Mono', 'JetBrainsMono-OFL.txt'),
    ('Noto Nastaliq Urdu', 'NotoNastaliqUrdu-OFL.txt'),
  ]) {
    yield LicenseEntryWithLineBreaks([pkg], await rootBundle.loadString('assets/fonts/$file'));
  }
}

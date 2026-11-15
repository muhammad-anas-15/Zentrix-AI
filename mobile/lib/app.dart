import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/l10n.dart';
import 'core/router/router.dart';
import 'core/theme/theme.dart';
import 'features/auth/application/session.dart';
import 'features/settings/application/preferences.dart';

class ZentrixApp extends ConsumerWidget {
  const ZentrixApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final prefs = ref.watch(preferencesProvider);
    final userLocale = ref.watch(currentUserProvider)?.locale;
    return MaterialApp.router(
      onGenerateTitle: (c) => c.l10n.appName,
      debugShowCheckedModeBanner: false,
      theme: zxLightTheme,
      darkTheme: zxDarkTheme,
      themeMode: prefs.themeMode,
      // the device choice wins; else the account's language; else the system's
      locale: prefs.locale ?? (userLocale == null ? null : Locale(userLocale)),
      supportedLocales: AppLocalizations.supportedLocales,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      routerConfig: ref.watch(routerProvider),
    );
  }
}

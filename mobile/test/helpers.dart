import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:zentrix/core/l10n.dart';
import 'package:zentrix/core/providers.dart';
import 'package:zentrix/core/storage/token_store.dart';
import 'package:zentrix/core/theme/theme.dart';

/// Pumps [child] inside the app's theme, localizations and a ProviderScope.
Future<ProviderContainer> pumpScreen(
  WidgetTester tester,
  Widget child, {
  List<Override> overrides = const [],
  Locale locale = const Locale('en'),
  TokenStore? tokens,
  bool reduceMotion = false,
}) async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();
  final scope = ProviderScope(
    overrides: [
      sharedPreferencesProvider.overrideWithValue(prefs),
      tokenStoreProvider.overrideWithValue(tokens ?? MemoryTokenStore()),
      ...overrides,
    ],
    retry: (_, _) => null,
    child: MaterialApp(
      theme: zxDarkTheme,
      locale: locale,
      supportedLocales: AppLocalizations.supportedLocales,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      home: child,
      builder: (context, page) => MediaQuery(
        data: MediaQuery.of(context).copyWith(disableAnimations: reduceMotion),
        child: page!,
      ),
    ),
  );
  await tester.pumpWidget(scope);
  await tester.pump();
  return ProviderScope.containerOf(tester.element(find.byType(MaterialApp)));
}

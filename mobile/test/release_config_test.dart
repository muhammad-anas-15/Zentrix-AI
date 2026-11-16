import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sentry_flutter/sentry_flutter.dart';
import 'package:zentrix/core/config/app_config.dart';
import 'package:zentrix/core/providers.dart';
import 'package:zentrix/core/telemetry.dart';
import 'package:zentrix/features/settings/presentation/settings_screen.dart';

import 'helpers.dart';

void main() {
  group('release builds', () {
    test('need an https API and never offer the developer sign-in', () {
      expect(
        () => AppConfig.forBuild(release: true, web: false, apiBaseUrl: 'http://api.example.com'),
        throwsStateError,
      );
      expect(() => AppConfig.forBuild(release: true, web: false), throwsStateError); // no URL at all
      final c = AppConfig.forBuild(
        release: true,
        web: false,
        apiBaseUrl: 'https://api.example.com',
        devLogin: true,
        devAutoSignIn: 'demo@example.com',
      );
      expect(c.apiBaseUrl, 'https://api.example.com');
      expect(c.devLogin, isFalse);
      expect(c.devAutoSignIn, isEmpty);
      expect(c.environment, 'prod');
    });

    test('debug builds keep the local defaults and the developer sign-in', () {
      final android = AppConfig.forBuild(release: false, web: false, devLogin: true);
      expect(android.apiBaseUrl, 'http://10.0.2.2:8000');
      expect(android.devLogin, isTrue);
      expect(AppConfig.forBuild(release: false, web: true).apiBaseUrl, 'http://127.0.0.1:8000');
      expect(android.environment, 'dev');
    });
  });

  test('error reports carry no user or request data', () async {
    final event = SentryEvent(
      user: SentryUser(id: 'u1', email: 'trader@example.com', ipAddress: '1.2.3.4'),
      request: SentryRequest(url: 'https://api/v1/me', headers: {'Authorization': 'Bearer t'}),
    );
    final out = await scrubEvent(event, Hint());
    expect(out!.user, isNull);
    expect(out.request, isNull);
  });

  testWidgets('Settings links to the privacy policy and terms when the build has them', (tester) async {
    await pumpScreen(
      tester,
      const SettingsScreen(),
      overrides: [
        appConfigProvider.overrideWithValue(
          const AppConfig(
            apiBaseUrl: 'http://test',
            privacyUrl: 'https://zentrix.example/privacy',
            termsUrl: 'https://zentrix.example/terms',
          ),
        ),
      ],
    );
    await tester.pump(const Duration(milliseconds: 50));
    await tester.scrollUntilVisible(find.text('Privacy policy'), 200, scrollable: find.byType(Scrollable).first);
    expect(find.text('Privacy policy'), findsOneWidget);
    expect(find.text('Terms of use'), findsOneWidget);
  });
}

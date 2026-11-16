import 'dart:async';

import 'package:sentry_flutter/sentry_flutter.dart';

import 'config/app_config.dart';

/// Crash and error reporting (Sentry). Off unless the build has `--dart-define=SENTRY_DSN=...`. Reports carry no
/// personal data: no user, no request headers, cookies or query strings, no screenshots or view hierarchy.
Future<void> runWithTelemetry(AppConfig config, void Function() runApp) async {
  if (config.sentryDsn.isEmpty) {
    runApp();
    return;
  }
  await SentryFlutter.init((o) {
    o.dsn = config.sentryDsn;
    o.environment = config.environment;
    o.sendDefaultPii = false;
    o.tracesSampleRate = 0;
    o.attachScreenshot = false;
    o.attachViewHierarchy = false;
    o.beforeSend = scrubEvent;
  }, appRunner: runApp);
}

/// Removes anything that could identify a person before an event leaves the device.
FutureOr<SentryEvent?> scrubEvent(SentryEvent event, Hint hint) {
  event
    ..user = null
    ..request = null;
  return event;
}

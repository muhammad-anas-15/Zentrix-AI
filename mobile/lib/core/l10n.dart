import 'package:flutter/widgets.dart';

import '../l10n/gen/app_localizations.dart';

export '../l10n/gen/app_localizations.dart';

extension L10nContext on BuildContext {
  AppLocalizations get l10n => AppLocalizations.of(this);

  /// Locale code for date formatting ("en", "ur").
  String get localeCode => Localizations.localeOf(this).languageCode;
}

/// Localized name of a strength tier; unknown tiers are shown as sent by the server.
String strengthLabel(AppLocalizations l, String strength) => switch (strength) {
  'Strong' => l.strengthStrong,
  'Good' => l.strengthGood,
  'Moderate' => l.strengthModerate,
  'Weak' => l.strengthWeak,
  'Very Weak - Wait' => l.strengthVeryWeak,
  _ => strength,
};

/// Localized title of a premium feature key.
String featureTitle(AppLocalizations l, String key) => switch (key) {
  'all_markets' => l.featureAllMarkets,
  'signal_alerts' => l.featureSignalAlerts,
  'trade_levels' => l.featureTradeLevels,
  'exit_advisor' => l.featureExitAdvisor,
  'scenario' => l.featureScenario,
  'journal' => l.featureJournal,
  'risk_guard' => l.featureRiskGuard,
  _ => key,
};

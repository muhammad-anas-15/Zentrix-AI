import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/providers.dart';

/// Device preferences: theme mode and app language (null = follow the system).
@immutable
class Preferences {
  const Preferences({this.themeMode = ThemeMode.dark, this.locale});

  final ThemeMode themeMode;
  final Locale? locale;

  Preferences copyWith({ThemeMode? themeMode, Locale? Function()? locale}) =>
      Preferences(themeMode: themeMode ?? this.themeMode, locale: locale != null ? locale() : this.locale);
}

class PreferencesController extends Notifier<Preferences> {
  static const _themeKey = 'zx_theme_mode';
  static const _localeKey = 'zx_locale';
  static const supportedLanguages = <String>['en', 'ur'];

  @override
  Preferences build() {
    final prefs = ref.watch(sharedPreferencesProvider);
    final theme = ThemeMode.values.asNameMap()[prefs.getString(_themeKey)] ?? ThemeMode.dark; // dark first
    final lang = prefs.getString(_localeKey);
    return Preferences(themeMode: theme, locale: supportedLanguages.contains(lang) ? Locale(lang!) : null);
  }

  Future<void> setThemeMode(ThemeMode mode) async {
    state = state.copyWith(themeMode: mode);
    await ref.read(sharedPreferencesProvider).setString(_themeKey, mode.name);
  }

  Future<void> setLanguage(String code) async {
    state = state.copyWith(locale: () => Locale(code));
    await ref.read(sharedPreferencesProvider).setString(_localeKey, code);
  }
}

final preferencesProvider = NotifierProvider<PreferencesController, Preferences>(PreferencesController.new);

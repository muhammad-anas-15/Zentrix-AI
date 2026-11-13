// Design tokens: the ONLY place with raw colours, sizes, type values and motion timings.
//
// Screens and widgets read these through `context.zx` (colours, text styles) and the
// `ZxSpace` / `ZxRadius` / `ZxSize` / `ZxMotion` constants. A test fails if a raw colour
// or font size appears outside lib/core/theme/. A new visual design (e.g. from Claude Design)
// is applied by changing this file, not the screens.

import 'dart:ui' show Brightness, FontFeature, FontWeight;

import 'package:flutter/foundation.dart' show immutable;
import 'package:flutter/painting.dart';

/// Spacing scale (logical pixels).
abstract final class ZxSpace {
  static const double xxs = 2;
  static const double xs = 4;
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 20;
  static const double xxl = 24;
  static const double xxxl = 32;
  static const double huge = 48;

  /// Horizontal page padding.
  static const double gutter = lg;
}

/// Corner radii.
abstract final class ZxRadius {
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 24;
  static const double pill = 999;
}

/// Fixed component sizes.
abstract final class ZxSize {
  static const double hairline = 1;
  static const double iconXs = 14;
  static const double iconSm = 16;
  static const double icon = 20;
  static const double iconLg = 24;
  static const double iconXl = 40;
  static const double tapTarget = 48;
  static const double lightDot = 12;
  static const double chartHeight = 300;
  static const double chartAxisWidth = 64;
  static const double sparkHeight = 36;
  static const double tickerWidth = 150;
  static const double maxContentWidth = 720;
  static const double progressStroke = 2;
  static const double breakdownBarHeight = 8;
}

/// Animation durations.
abstract final class ZxMotion {
  static const Duration fast = Duration(milliseconds: 150);
  static const Duration normal = Duration(milliseconds: 250);
  static const Duration slow = Duration(milliseconds: 400);
}

/// Surface effects.
abstract final class ZxEffects {
  /// Backdrop blur (sigma) for glass surfaces that float over content.
  static const double glassBlur = 18;

  /// Soft glow behind the page (radius as a fraction of the screen).
  static const double glowRadius = 0.9;
}

/// Colour palette. One instance per brightness; widgets never pick a raw colour.
@immutable
class ZxPalette {
  const ZxPalette({
    required this.brightness,
    required this.background,
    required this.backgroundAlt,
    required this.glowPrimary,
    required this.glowSecondary,
    required this.surface,
    required this.surfaceRaised,
    required this.glass,
    required this.glassStrong,
    required this.glassBorder,
    required this.divider,
    required this.textPrimary,
    required this.textSecondary,
    required this.textMuted,
    required this.textOnAccent,
    required this.accent,
    required this.accentAlt,
    required this.accentSoft,
    required this.gold,
    required this.goldSoft,
    required this.bullish,
    required this.bullishSoft,
    required this.bearish,
    required this.bearishSoft,
    required this.caution,
    required this.cautionSoft,
    required this.neutral,
    required this.neutralSoft,
    required this.chartGrid,
    required this.chartCrosshair,
    required this.scrim,
  });

  final Brightness brightness;

  // Page
  final Color background;
  final Color backgroundAlt;
  final Color glowPrimary;
  final Color glowSecondary;

  // Surfaces
  final Color surface;
  final Color surfaceRaised;
  final Color glass;
  final Color glassStrong;
  final Color glassBorder;
  final Color divider;

  // Text
  final Color textPrimary;
  final Color textSecondary;
  final Color textMuted;
  final Color textOnAccent;

  // Actions and badges
  final Color accent; // violet: primary actions
  final Color accentAlt; // indigo: secondary emphasis
  final Color accentSoft;
  final Color gold; // Premium badge
  final Color goldSoft;

  // Semantic
  final Color bullish; // emerald: up, success
  final Color bullishSoft;
  final Color bearish; // coral / crimson: down, danger
  final Color bearishSoft;
  final Color caution; // amber: warnings, news caution
  final Color cautionSoft;
  final Color neutral; // grey: "Very Weak - Wait", unknown
  final Color neutralSoft;

  // Charts and overlays
  final Color chartGrid;
  final Color chartCrosshair;
  final Color scrim;

  static const ZxPalette dark = ZxPalette(
    brightness: Brightness.dark,
    background: Color(0xFF0A0C11),
    backgroundAlt: Color(0xFF10131B),
    glowPrimary: Color(0x2E7C5CFA),
    glowSecondary: Color(0x1A10B981),
    surface: Color(0xFF141824),
    surfaceRaised: Color(0xFF1B2030),
    glass: Color(0x0FFFFFFF),
    glassStrong: Color(0x1AFFFFFF),
    glassBorder: Color(0x1FFFFFFF),
    divider: Color(0x14FFFFFF),
    textPrimary: Color(0xFFF2F4F8),
    textSecondary: Color(0xFFAAB1C5),
    textMuted: Color(0xFF7A819B),
    textOnAccent: Color(0xFFFFFFFF),
    accent: Color(0xFF7A5AF8), // white label >= 4.5:1
    accentAlt: Color(0xFF6366F1),
    accentSoft: Color(0x337A5AF8),
    gold: Color(0xFFE9B949),
    goldSoft: Color(0x29E9B949),
    bullish: Color(0xFF10B981),
    bullishSoft: Color(0x2410B981),
    bearish: Color(0xFFF2596D),
    bearishSoft: Color(0x24F2596D),
    caution: Color(0xFFF5A524),
    cautionSoft: Color(0x24F5A524),
    neutral: Color(0xFF8E94AA),
    neutralSoft: Color(0x248E94AA),
    chartGrid: Color(0x12FFFFFF),
    chartCrosshair: Color(0x66FFFFFF),
    scrim: Color(0x99000000),
  );

  static const ZxPalette light = ZxPalette(
    brightness: Brightness.light,
    background: Color(0xFFF5F6FA),
    backgroundAlt: Color(0xFFECEEF5),
    glowPrimary: Color(0x1F7C3AED),
    glowSecondary: Color(0x14059669),
    surface: Color(0xFFFFFFFF),
    surfaceRaised: Color(0xFFFFFFFF),
    glass: Color(0xB8FFFFFF),
    glassStrong: Color(0xE6FFFFFF),
    glassBorder: Color(0x1A1B2030),
    divider: Color(0x141B2030),
    textPrimary: Color(0xFF12141C),
    textSecondary: Color(0xFF474D63),
    textMuted: Color(0xFF6E748C),
    textOnAccent: Color(0xFFFFFFFF),
    accent: Color(0xFF7C3AED),
    accentAlt: Color(0xFF4F46E5),
    accentSoft: Color(0x1F7C3AED),
    gold: Color(0xFF9A6B00),
    goldSoft: Color(0x24B7861C),
    bullish: Color(0xFF047857),
    bullishSoft: Color(0x1F059669),
    bearish: Color(0xFFC8293F),
    bearishSoft: Color(0x1FDC3B52),
    caution: Color(0xFF9A5B00),
    cautionSoft: Color(0x24B97800),
    neutral: Color(0xFF5F6580),
    neutralSoft: Color(0x1F6B7187),
    chartGrid: Color(0x141B2030),
    chartCrosshair: Color(0x661B2030),
    scrim: Color(0x66000000),
  );
}

/// Type scale (sizes, weights, spacing). Colours are applied in theme.dart.
abstract final class ZxType {
  /// Platform font (Roboto on Android) until a font is bundled; set the family name here.
  static const String? fontFamily = null;

  /// Fallbacks for Urdu script (system Nastaliq/Naskh faces).
  static const List<String> fontFallback = <String>['Noto Nastaliq Urdu', 'Noto Naskh Arabic'];

  /// Prices and metrics line up in columns.
  static const List<FontFeature> tabular = <FontFeature>[FontFeature.tabularFigures()];

  static const double displaySize = 32;
  static const double headlineSize = 24;
  static const double titleSize = 18;
  static const double bodySize = 15;
  static const double labelSize = 13;
  static const double captionSize = 12;
  static const double overlineSize = 11;
  static const double priceSize = 30;
  static const double metricSize = 20;
  static const double metricSmallSize = 16;
  static const double chartLabelSize = 10;

  static const FontWeight regular = FontWeight.w400;
  static const FontWeight medium = FontWeight.w500;
  static const FontWeight semibold = FontWeight.w600;
  static const FontWeight bold = FontWeight.w700;

  static const double tightLetterSpacing = -0.4;
  static const double wideLetterSpacing = 0.8;
  static const double bodyHeight = 1.4;
}

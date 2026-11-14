// Design tokens: the ONLY place with raw colours, sizes, type values and motion timings.
//
// Screens and widgets read these through `context.zx` (colours, text styles) and the
// `ZxSpace` / `ZxRadius` / `ZxSize` / `ZxMotion` / `ZxEffects` constants. A test fails if a raw colour
// or font size appears outside lib/core/theme/. A new visual design (e.g. from Claude Design)
// is applied by changing this file, not the screens.

import 'dart:ui' show Brightness, FontFeature, FontWeight;

import 'package:flutter/animation.dart' show Curve, Curves;
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

  /// Space kept free under scrolling content for the floating navigation bar.
  static const double navClearance = 112;
}

/// Corner radii.
abstract final class ZxRadius {
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 18;
  static const double xl = 26;
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
  static const double orb = 14;
  static const double orbLarge = 18;
  static const double chartHeight = 300;
  static const double chartAxisWidth = 64;
  static const double heroChartHeight = 96;
  static const double fanChartHeight = 132;
  static const double sparkHeight = 36;
  static const double rowSparkWidth = 64;
  static const double rowSparkHeight = 28;
  static const double tickerWidth = 150;
  static const double ring = 64;
  static const double ringStroke = 5;
  static const double maxContentWidth = 720;
  static const double progressStroke = 2;
  static const double breakdownBarHeight = 8;
  static const double segmentHeight = 40;
  static const double navHeight = 68;
  static const double skeletonLine = 14;
}

/// Animation timings and curves. Widgets skip pulses, flashes and shimmer when the system asks for reduced motion.
abstract final class ZxMotion {
  static const Duration fast = Duration(milliseconds: 150);
  static const Duration normal = Duration(milliseconds: 250);
  static const Duration slow = Duration(milliseconds: 400);
  static const Duration entrance = Duration(milliseconds: 420);
  static const Duration stagger = Duration(milliseconds: 45);
  static const Duration flash = Duration(milliseconds: 900);
  static const Duration pulse = Duration(milliseconds: 1800);
  static const Duration shimmer = Duration(milliseconds: 1400);

  static const Curve emphasized = Curves.easeOutCubic;
  static const Curve standard = Curves.easeInOut;
  static const Curve slide = Curves.easeOutBack;

  /// Distance (px) items travel while fading in.
  static const double entranceOffset = 14;
}

/// Surface depth: base (flat glass), raised (cards that matter), floating (bars and sheets over content).
enum ZxLevel { base, raised, floating }

/// Surface effects.
abstract final class ZxEffects {
  /// Backdrop blur (sigma) for floating surfaces (navigation bar, app bar, sheets). Only these blur.
  static const double glassBlur = 22;

  /// Soft glow behind the page (radius as a fraction of the screen).
  static const double glowRadius = 0.9;

  /// Coloured glow around a state element (condition orb, live price flash).
  static const double glowBlur = 18;
  static const double orbGlowBlur = 14;

  /// Shadows per level.
  static const double raisedShadowBlur = 28;
  static const double raisedShadowOffset = 10;
  static const double floatingShadowBlur = 40;
  static const double floatingShadowOffset = 14;

  /// Alpha of the semantic tint washed into a card that carries a state (0-1).
  static const double stateTint = 0.10;

  /// Alpha of an accent border on a highlighted card (0-1).
  static const double accentBorder = 0.55;
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
    required this.glassFloating,
    required this.glassBorder,
    required this.highlight,
    required this.shadow,
    required this.divider,
    required this.textPrimary,
    required this.textSecondary,
    required this.textMuted,
    required this.textOnAccent,
    required this.accent,
    required this.accentAlt,
    required this.accentSoft,
    required this.gold,
    required this.goldDeep,
    required this.goldSoft,
    required this.bullish,
    required this.bullishDeep,
    required this.bullishSoft,
    required this.bearish,
    required this.bearishDeep,
    required this.bearishSoft,
    required this.caution,
    required this.cautionSoft,
    required this.neutral,
    required this.neutralSoft,
    required this.chartGrid,
    required this.chartCrosshair,
    required this.scrim,
    required this.skeleton,
    required this.skeletonShine,
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
  final Color glass; // base level
  final Color glassStrong; // raised level, top of the card gradient
  final Color glassFloating; // floating bars (with blur)
  final Color glassBorder;
  final Color highlight; // light catching the top edge of a glass surface
  final Color shadow;
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
  final Color goldDeep;
  final Color goldSoft;

  // Semantic: state of the market, never signal quality
  final Color bullish; // emerald: up, success
  final Color bullishDeep; // teal end of the up gradient
  final Color bullishSoft;
  final Color bearish; // coral: down, danger
  final Color bearishDeep; // crimson end of the down gradient
  final Color bearishSoft;
  final Color caution; // amber: warnings, news caution
  final Color cautionSoft;
  final Color neutral; // grey: "Very Weak - Wait", unknown
  final Color neutralSoft;

  // Charts and overlays
  final Color chartGrid;
  final Color chartCrosshair;
  final Color scrim;
  final Color skeleton;
  final Color skeletonShine;

  LinearGradient get accentGradient => LinearGradient(colors: [accent, accentAlt]);
  LinearGradient get upGradient => LinearGradient(colors: [bullish, bullishDeep]);
  LinearGradient get downGradient => LinearGradient(colors: [bearish, bearishDeep]);
  LinearGradient get goldGradient => LinearGradient(colors: [gold, goldDeep]);

  static const ZxPalette dark = ZxPalette(
    brightness: Brightness.dark,
    background: Color(0xFF07090E),
    backgroundAlt: Color(0xFF0E1119),
    glowPrimary: Color(0x337A5AF8),
    glowSecondary: Color(0x1C10B981),
    surface: Color(0xFF131722),
    surfaceRaised: Color(0xFF1A1F2E),
    glass: Color(0x0DFFFFFF),
    glassStrong: Color(0x1CFFFFFF),
    glassFloating: Color(0xB80C0F17),
    glassBorder: Color(0x1FFFFFFF),
    highlight: Color(0x40FFFFFF),
    shadow: Color(0x73000000),
    divider: Color(0x14FFFFFF),
    textPrimary: Color(0xFFF4F6FA),
    textSecondary: Color(0xFFAAB1C5),
    textMuted: Color(0xFF7A819B),
    textOnAccent: Color(0xFFFFFFFF),
    accent: Color(0xFF7A5AF8), // white label >= 4.5:1
    accentAlt: Color(0xFF5B63F0),
    accentSoft: Color(0x337A5AF8),
    gold: Color(0xFFE9B949),
    goldDeep: Color(0xFFC98A1B),
    goldSoft: Color(0x29E9B949),
    bullish: Color(0xFF10B981),
    bullishDeep: Color(0xFF0EA5A4),
    bullishSoft: Color(0x2410B981),
    bearish: Color(0xFFF2596D),
    bearishDeep: Color(0xFFD9364F),
    bearishSoft: Color(0x24F2596D),
    caution: Color(0xFFF5A524),
    cautionSoft: Color(0x24F5A524),
    neutral: Color(0xFF8E94AA),
    neutralSoft: Color(0x248E94AA),
    chartGrid: Color(0x12FFFFFF),
    chartCrosshair: Color(0x66FFFFFF),
    scrim: Color(0x99000000),
    skeleton: Color(0x12FFFFFF),
    skeletonShine: Color(0x24FFFFFF),
  );

  static const ZxPalette light = ZxPalette(
    brightness: Brightness.light,
    background: Color(0xFFF4F5FA),
    backgroundAlt: Color(0xFFEBEDF5),
    glowPrimary: Color(0x247C3AED),
    glowSecondary: Color(0x16059669),
    surface: Color(0xFFFFFFFF),
    surfaceRaised: Color(0xFFFFFFFF),
    glass: Color(0xB8FFFFFF),
    glassStrong: Color(0xF2FFFFFF),
    glassFloating: Color(0xD9FFFFFF),
    glassBorder: Color(0x1A1B2030),
    highlight: Color(0xFFFFFFFF),
    shadow: Color(0x1F1B2030),
    divider: Color(0x141B2030),
    textPrimary: Color(0xFF11131B),
    textSecondary: Color(0xFF474D63),
    textMuted: Color(0xFF6E748C),
    textOnAccent: Color(0xFFFFFFFF),
    accent: Color(0xFF7C3AED),
    accentAlt: Color(0xFF4F46E5),
    accentSoft: Color(0x1F7C3AED),
    gold: Color(0xFF9A6B00),
    goldDeep: Color(0xFF7A5200),
    goldSoft: Color(0x24B7861C),
    bullish: Color(0xFF047857),
    bullishDeep: Color(0xFF0F766E),
    bullishSoft: Color(0x1F059669),
    bearish: Color(0xFFC8293F),
    bearishDeep: Color(0xFFA51D33),
    bearishSoft: Color(0x1FDC3B52),
    caution: Color(0xFF9A5B00),
    cautionSoft: Color(0x24B97800),
    neutral: Color(0xFF5F6580),
    neutralSoft: Color(0x1F6B7187),
    chartGrid: Color(0x141B2030),
    chartCrosshair: Color(0x661B2030),
    scrim: Color(0x66000000),
    skeleton: Color(0x0F1B2030),
    skeletonShine: Color(0x1F1B2030),
  );
}

/// Type scale (families, sizes, weights, spacing). Colours are applied in theme.dart.
abstract final class ZxType {
  /// Interface text (bundled: assets/fonts, OFL).
  static const String fontFamily = 'Inter';

  /// Prices and live figures.
  static const String monoFamily = 'JetBrainsMono';

  /// Urdu script: Inter has no Arabic glyphs, so Urdu text falls back to Nastaliq automatically.
  static const List<String> fontFallback = <String>['NotoNastaliqUrdu'];

  /// Metrics line up in columns.
  static const List<FontFeature> tabular = <FontFeature>[FontFeature.tabularFigures()];

  static const double displaySize = 32;
  static const double headlineSize = 24;
  static const double titleSize = 18;
  static const double bodySize = 15;
  static const double labelSize = 13;
  static const double captionSize = 12;
  static const double overlineSize = 11;
  static const double heroPriceSize = 38;
  static const double priceSize = 28;
  static const double priceSmallSize = 15;
  static const double metricSize = 20;
  static const double metricSmallSize = 16;
  static const double chartLabelSize = 10;

  static const FontWeight regular = FontWeight.w400;
  static const FontWeight medium = FontWeight.w500;
  static const FontWeight semibold = FontWeight.w600;
  static const FontWeight bold = FontWeight.w700;

  static const double tightLetterSpacing = -0.6;
  static const double priceLetterSpacing = -1.2;
  static const double wideLetterSpacing = 1.1;
  static const double bodyHeight = 1.4;
  static const double numberHeight = 1.15;
}

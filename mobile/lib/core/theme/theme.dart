// Builds ThemeData and the ZxTheme extension from the design tokens.

import 'package:flutter/cupertino.dart' show CupertinoPageTransitionsBuilder;
import 'package:flutter/material.dart';

import 'tokens.dart';

/// Semantic colours and text styles for widgets: `context.zx`.
@immutable
class ZxTheme extends ThemeExtension<ZxTheme> {
  const ZxTheme({required this.palette, required this.text});

  final ZxPalette palette;
  final ZxTextStyles text;

  @override
  ZxTheme copyWith({ZxPalette? palette, ZxTextStyles? text}) =>
      ZxTheme(palette: palette ?? this.palette, text: text ?? this.text);

  @override
  ZxTheme lerp(ThemeExtension<ZxTheme>? other, double t) => t < 0.5 ? this : (other as ZxTheme? ?? this);
}

/// The type scale with colours applied.
@immutable
class ZxTextStyles {
  const ZxTextStyles({
    required this.display,
    required this.headline,
    required this.title,
    required this.body,
    required this.bodyStrong,
    required this.secondary,
    required this.label,
    required this.caption,
    required this.overline,
    required this.heroPrice,
    required this.price,
    required this.priceSmall,
    required this.metric,
    required this.metricSmall,
    required this.chartLabel,
  });

  factory ZxTextStyles.from(ZxPalette p) {
    TextStyle base(double size, FontWeight weight, Color color, {double? spacing, bool tabular = false}) => TextStyle(
      fontFamily: ZxType.fontFamily,
      fontFamilyFallback: ZxType.fontFallback,
      fontSize: size,
      fontWeight: weight,
      color: color,
      letterSpacing: spacing,
      height: ZxType.bodyHeight,
      fontFeatures: tabular ? ZxType.tabular : null,
    );
    // Prices and live figures: monospaced, tight, so digits never jump as they change.
    TextStyle mono(double size, FontWeight weight, Color color, {double? spacing}) => TextStyle(
      fontFamily: ZxType.monoFamily,
      fontFamilyFallback: ZxType.fontFallback,
      fontSize: size,
      fontWeight: weight,
      color: color,
      letterSpacing: spacing,
      height: ZxType.numberHeight,
    );
    return ZxTextStyles(
      display: base(ZxType.displaySize, ZxType.bold, p.textPrimary, spacing: ZxType.tightLetterSpacing),
      headline: base(ZxType.headlineSize, ZxType.bold, p.textPrimary, spacing: ZxType.tightLetterSpacing),
      title: base(ZxType.titleSize, ZxType.semibold, p.textPrimary),
      body: base(ZxType.bodySize, ZxType.regular, p.textPrimary),
      bodyStrong: base(ZxType.bodySize, ZxType.semibold, p.textPrimary),
      secondary: base(ZxType.bodySize, ZxType.regular, p.textSecondary),
      label: base(ZxType.labelSize, ZxType.semibold, p.textSecondary),
      caption: base(ZxType.captionSize, ZxType.regular, p.textMuted),
      overline: base(ZxType.overlineSize, ZxType.bold, p.textMuted, spacing: ZxType.wideLetterSpacing),
      heroPrice: mono(ZxType.heroPriceSize, ZxType.bold, p.textPrimary, spacing: ZxType.priceLetterSpacing),
      price: mono(ZxType.priceSize, ZxType.bold, p.textPrimary, spacing: ZxType.priceLetterSpacing),
      priceSmall: mono(ZxType.priceSmallSize, ZxType.medium, p.textPrimary),
      metric: base(ZxType.metricSize, ZxType.semibold, p.textPrimary, tabular: true),
      metricSmall: base(ZxType.metricSmallSize, ZxType.semibold, p.textPrimary, tabular: true),
      chartLabel: mono(ZxType.chartLabelSize, ZxType.medium, p.textMuted),
    );
  }

  final TextStyle display;
  final TextStyle headline;
  final TextStyle title;
  final TextStyle body;
  final TextStyle bodyStrong;
  final TextStyle secondary;
  final TextStyle label;
  final TextStyle caption;
  final TextStyle overline;
  final TextStyle heroPrice;
  final TextStyle price;
  final TextStyle priceSmall;
  final TextStyle metric;
  final TextStyle metricSmall;
  final TextStyle chartLabel;
}

extension ZxThemeContext on BuildContext {
  ZxTheme get zx => Theme.of(this).extension<ZxTheme>()!;
}

/// Material theme from a palette. Component themes use only tokens.
ThemeData buildTheme(ZxPalette p) {
  final text = ZxTextStyles.from(p);
  final scheme = ColorScheme(
    brightness: p.brightness,
    primary: p.accent,
    onPrimary: p.textOnAccent,
    secondary: p.accentAlt,
    onSecondary: p.textOnAccent,
    tertiary: p.gold,
    onTertiary: p.background,
    error: p.bearish,
    onError: p.textOnAccent,
    surface: p.surface,
    onSurface: p.textPrimary,
    onSurfaceVariant: p.textSecondary,
    surfaceContainerLowest: p.background,
    surfaceContainerLow: p.backgroundAlt,
    surfaceContainer: p.surface,
    surfaceContainerHigh: p.surfaceRaised,
    surfaceContainerHighest: p.surfaceRaised,
    outline: p.glassBorder,
    outlineVariant: p.divider,
    shadow: p.scrim,
    scrim: p.scrim,
    inverseSurface: p.textPrimary,
    onInverseSurface: p.background,
    inversePrimary: p.accentSoft,
  );
  final rounded = RoundedRectangleBorder(borderRadius: BorderRadius.circular(ZxRadius.md));
  final glassBorder = OutlineInputBorder(
    borderRadius: BorderRadius.circular(ZxRadius.md),
    borderSide: BorderSide(color: p.glassBorder, width: ZxSize.hairline),
  );
  return ThemeData(
    useMaterial3: true,
    brightness: p.brightness,
    colorScheme: scheme,
    fontFamily: ZxType.fontFamily,
    fontFamilyFallback: ZxType.fontFallback,
    scaffoldBackgroundColor: p.background,
    canvasColor: p.background,
    dividerColor: p.divider,
    splashFactory: InkSparkle.splashFactory,
    extensions: <ThemeExtension<dynamic>>[ZxTheme(palette: p, text: text)],
    textTheme: TextTheme(
      displaySmall: text.display,
      headlineSmall: text.headline,
      titleLarge: text.title,
      titleMedium: text.bodyStrong,
      titleSmall: text.label,
      bodyLarge: text.body,
      bodyMedium: text.body,
      bodySmall: text.caption,
      labelLarge: text.bodyStrong,
      labelMedium: text.label,
      labelSmall: text.overline,
    ),
    appBarTheme: AppBarTheme(
      backgroundColor: p.background.withValues(alpha: 0),
      surfaceTintColor: p.background.withValues(alpha: 0),
      foregroundColor: p.textPrimary,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: false,
      titleTextStyle: text.title,
    ),
    cardTheme: CardThemeData(
      color: p.glass,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(ZxRadius.lg),
        side: BorderSide(color: p.glassBorder, width: ZxSize.hairline),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: p.glass,
      labelStyle: text.label,
      hintStyle: text.caption,
      helperStyle: text.caption,
      errorStyle: text.caption.copyWith(color: p.bearish),
      contentPadding: const EdgeInsets.symmetric(horizontal: ZxSpace.lg, vertical: ZxSpace.md),
      border: glassBorder,
      enabledBorder: glassBorder,
      focusedBorder: glassBorder.copyWith(
        borderSide: BorderSide(color: p.accent, width: ZxSize.hairline * 1.5),
      ),
      errorBorder: glassBorder.copyWith(
        borderSide: BorderSide(color: p.bearish, width: ZxSize.hairline),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: p.accent,
        foregroundColor: p.textOnAccent,
        disabledBackgroundColor: p.glassStrong,
        minimumSize: const Size.fromHeight(ZxSize.tapTarget),
        textStyle: text.bodyStrong,
        shape: rounded,
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: p.textPrimary,
        minimumSize: const Size.fromHeight(ZxSize.tapTarget),
        side: BorderSide(color: p.glassBorder, width: ZxSize.hairline),
        textStyle: text.bodyStrong,
        shape: rounded,
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(foregroundColor: p.accent, textStyle: text.label),
    ),
    segmentedButtonTheme: SegmentedButtonThemeData(
      style: ButtonStyle(
        textStyle: WidgetStatePropertyAll(text.label),
        side: WidgetStatePropertyAll(BorderSide(color: p.glassBorder, width: ZxSize.hairline)),
        backgroundColor: WidgetStateProperty.resolveWith(
          (s) => s.contains(WidgetState.selected) ? p.accentSoft : p.glass,
        ),
        foregroundColor: WidgetStateProperty.resolveWith(
          (s) => s.contains(WidgetState.selected) ? p.textPrimary : p.textSecondary,
        ),
      ),
    ),
    chipTheme: ChipThemeData(
      backgroundColor: p.glass,
      selectedColor: p.accentSoft,
      side: BorderSide(color: p.glassBorder, width: ZxSize.hairline),
      labelStyle: text.label,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(ZxRadius.pill)),
      padding: const EdgeInsets.symmetric(horizontal: ZxSpace.sm),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: p.backgroundAlt.withValues(alpha: 0), // painted by the glass bar
      surfaceTintColor: p.backgroundAlt.withValues(alpha: 0),
      height: ZxSize.navHeight,
      indicatorColor: p.accentSoft,
      elevation: 0,
      labelTextStyle: WidgetStateProperty.resolveWith(
        (s) => text.caption.copyWith(
          color: s.contains(WidgetState.selected) ? p.textPrimary : p.textMuted,
          fontWeight: s.contains(WidgetState.selected) ? ZxType.semibold : ZxType.regular,
        ),
      ),
      iconTheme: WidgetStateProperty.resolveWith(
        (s) => IconThemeData(color: s.contains(WidgetState.selected) ? p.textPrimary : p.textMuted),
      ),
    ),
    // Tabs: a sliding gradient pill, like the segmented controls.
    tabBarTheme: TabBarThemeData(
      labelStyle: text.label,
      unselectedLabelStyle: text.label,
      labelColor: p.textOnAccent,
      unselectedLabelColor: p.textSecondary,
      indicatorSize: TabBarIndicatorSize.tab,
      indicator: BoxDecoration(gradient: p.accentGradient, borderRadius: BorderRadius.circular(ZxRadius.pill)),
      dividerColor: p.divider.withValues(alpha: 0),
      splashBorderRadius: BorderRadius.circular(ZxRadius.pill),
      labelPadding: const EdgeInsets.symmetric(horizontal: ZxSpace.md),
    ),
    pageTransitionsTheme: const PageTransitionsTheme(
      builders: {
        TargetPlatform.android: FadeForwardsPageTransitionsBuilder(),
        TargetPlatform.iOS: CupertinoPageTransitionsBuilder(),
        TargetPlatform.macOS: CupertinoPageTransitionsBuilder(),
        TargetPlatform.windows: FadeForwardsPageTransitionsBuilder(),
        TargetPlatform.linux: FadeForwardsPageTransitionsBuilder(),
      },
    ),
    listTileTheme: ListTileThemeData(
      iconColor: p.textSecondary,
      textColor: p.textPrimary,
      titleTextStyle: text.body,
      subtitleTextStyle: text.caption,
      contentPadding: const EdgeInsets.symmetric(horizontal: ZxSpace.lg),
    ),
    switchTheme: SwitchThemeData(
      thumbColor: WidgetStateProperty.resolveWith(
        (s) => s.contains(WidgetState.selected) ? p.textOnAccent : p.textMuted,
      ),
      trackColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? p.accent : p.glassStrong),
      trackOutlineColor: WidgetStatePropertyAll(p.glassBorder),
    ),
    dividerTheme: DividerThemeData(color: p.divider, thickness: ZxSize.hairline, space: ZxSpace.lg),
    dialogTheme: DialogThemeData(
      backgroundColor: p.surfaceRaised,
      surfaceTintColor: p.surfaceRaised,
      titleTextStyle: text.title,
      contentTextStyle: text.secondary,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(ZxRadius.xl)),
    ),
    bottomSheetTheme: BottomSheetThemeData(
      backgroundColor: p.surfaceRaised,
      surfaceTintColor: p.surfaceRaised,
      showDragHandle: true,
      dragHandleColor: p.glassBorder,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(ZxRadius.xl))),
    ),
    snackBarTheme: SnackBarThemeData(
      backgroundColor: p.surfaceRaised,
      contentTextStyle: text.body,
      behavior: SnackBarBehavior.floating,
      shape: rounded,
    ),
    progressIndicatorTheme: ProgressIndicatorThemeData(color: p.accent, linearTrackColor: p.glassStrong),
    floatingActionButtonTheme: FloatingActionButtonThemeData(
      backgroundColor: p.accent,
      foregroundColor: p.textOnAccent,
      shape: rounded,
    ),
    iconTheme: IconThemeData(color: p.textSecondary, size: ZxSize.icon),
  );
}

/// Dark first: the default experience.
final ThemeData zxDarkTheme = buildTheme(ZxPalette.dark);
final ThemeData zxLightTheme = buildTheme(ZxPalette.light);

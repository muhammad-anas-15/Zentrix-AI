import 'dart:ui' show ImageFilter;

import 'package:flutter/material.dart';

import '../l10n.dart';
import '../theme/theme.dart';
import '../theme/tokens.dart';

/// Page background: obsidian base with two soft glows.
class ZxBackground extends StatelessWidget {
  const ZxBackground({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final p = context.zx.palette;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: p.background,
        gradient: RadialGradient(
          center: AlignmentDirectional.topStart.resolve(Directionality.of(context)),
          radius: ZxEffects.glowRadius,
          colors: [p.glowPrimary, p.glowPrimary.withValues(alpha: 0)],
        ),
      ),
      child: DecoratedBox(
        decoration: BoxDecoration(
          gradient: RadialGradient(
            center: AlignmentDirectional.bottomEnd.resolve(Directionality.of(context)),
            radius: ZxEffects.glowRadius,
            colors: [p.glowSecondary, p.glowSecondary.withValues(alpha: 0)],
          ),
        ),
        child: child,
      ),
    );
  }
}

/// Standard scrolling page: app bar, glow background, centred content column with token spacing.
class ZxPage extends StatelessWidget {
  const ZxPage({
    super.key,
    this.title,
    this.actions,
    required this.children,
    this.onRefresh,
    this.floatingActionButton,
    this.bottom,
    this.leading,
  });

  final String? title;
  final List<Widget>? actions;
  final List<Widget> children;
  final Future<void> Function()? onRefresh;
  final Widget? floatingActionButton;
  final PreferredSizeWidget? bottom;
  final Widget? leading;

  @override
  Widget build(BuildContext context) {
    Widget list = ListView.separated(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(ZxSpace.gutter, ZxSpace.sm, ZxSpace.gutter, ZxSpace.huge * 2),
      itemCount: children.length,
      separatorBuilder: (_, _) => const SizedBox(height: ZxSpace.md),
      itemBuilder: (_, i) => children[i],
    );
    if (onRefresh != null) list = RefreshIndicator(onRefresh: onRefresh!, child: list);
    return Scaffold(
      appBar: title == null ? null : AppBar(title: Text(title!), actions: actions, bottom: bottom, leading: leading),
      floatingActionButton: floatingActionButton,
      body: ZxBackground(
        child: SafeArea(
          top: title == null,
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: ZxSize.maxContentWidth),
              child: list,
            ),
          ),
        ),
      ),
    );
  }
}

/// Translucent "glass" card with a subtle border. `accent` tints the border for emphasis.
class GlassCard extends StatelessWidget {
  const GlassCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(ZxSpace.lg),
    this.onTap,
    this.accent,
    this.blur = false,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;
  final VoidCallback? onTap;
  final Color? accent;

  /// Backdrop blur, for cards floating over content (costly; off by default).
  final bool blur;

  @override
  Widget build(BuildContext context) {
    final p = context.zx.palette;
    final radius = BorderRadius.circular(ZxRadius.lg);
    Widget body = DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: radius,
        gradient: LinearGradient(
          begin: AlignmentDirectional.topStart.resolve(Directionality.of(context)),
          end: AlignmentDirectional.bottomEnd.resolve(Directionality.of(context)),
          colors: [p.glassStrong, p.glass],
        ),
        border: Border.all(color: accent?.withValues(alpha: 0.55) ?? p.glassBorder, width: ZxSize.hairline),
      ),
      child: Padding(padding: padding, child: child),
    );
    if (onTap != null) {
      body = Material(
        type: MaterialType.transparency,
        child: InkWell(borderRadius: radius, onTap: onTap, child: body),
      );
    }
    if (blur) {
      body = ClipRRect(
        borderRadius: radius,
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: ZxEffects.glassBlur, sigmaY: ZxEffects.glassBlur),
          child: body,
        ),
      );
    }
    return body;
  }
}

class SectionHeader extends StatelessWidget {
  const SectionHeader(this.title, {super.key, this.trailing});

  final String title;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: ZxSpace.sm),
    child: Row(
      children: [
        Expanded(child: Text(title, style: context.zx.text.title)),
        ?trailing,
      ],
    ),
  );
}

/// Label + big tabular value (+ optional caption).
class MetricTile extends StatelessWidget {
  const MetricTile({super.key, required this.label, required this.value, this.valueColor, this.caption});

  final String label;
  final String value;
  final Color? valueColor;
  final String? caption;

  @override
  Widget build(BuildContext context) {
    final t = context.zx.text;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(label.toUpperCase(), style: t.overline),
        const SizedBox(height: ZxSpace.xs),
        Text(value, style: t.metric.copyWith(color: valueColor)),
        if (caption != null) ...[const SizedBox(height: ZxSpace.xxs), Text(caption!, style: t.caption)],
      ],
    );
  }
}

/// Metric tiles in a responsive grid (2 columns on phones).
class MetricGrid extends StatelessWidget {
  const MetricGrid({super.key, required this.tiles, this.columns = 2});

  final List<Widget> tiles;
  final int columns;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, c) {
      final cols = c.maxWidth > 520 ? columns + 1 : columns;
      final width = (c.maxWidth - ZxSpace.lg * (cols - 1)) / cols;
      return Wrap(
        spacing: ZxSpace.lg,
        runSpacing: ZxSpace.lg,
        children: [for (final t in tiles) SizedBox(width: width, child: t)],
      );
    },
  );
}

/// Small coloured capsule (badges, chips).
class Pill extends StatelessWidget {
  const Pill({super.key, required this.label, required this.color, required this.background, this.icon});

  final String label;
  final Color color;
  final Color background;
  final IconData? icon;

  @override
  Widget build(BuildContext context) => DecoratedBox(
    decoration: BoxDecoration(
      color: background,
      borderRadius: BorderRadius.circular(ZxRadius.pill),
      border: Border.all(color: color.withValues(alpha: 0.35), width: ZxSize.hairline),
    ),
    child: Padding(
      padding: const EdgeInsets.symmetric(horizontal: ZxSpace.sm, vertical: ZxSpace.xxs),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[Icon(icon, size: ZxSize.iconXs, color: color), const SizedBox(width: ZxSpace.xs)],
          Text(label, style: context.zx.text.label.copyWith(color: color)),
        ],
      ),
    ),
  );
}

/// "Not financial advice." line (or a longer note).
class Disclaimer extends StatelessWidget {
  const Disclaimer({super.key, this.text});

  final String? text;

  @override
  Widget build(BuildContext context) => Row(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Icon(Icons.info_outline, size: ZxSize.iconSm, color: context.zx.palette.textMuted),
      const SizedBox(width: ZxSpace.sm),
      Expanded(child: Text(text ?? context.l10n.notFinancialAdvice, style: context.zx.text.caption)),
    ],
  );
}

/// Two-sided proportion bar (e.g. wins vs losses).
class BreakdownBar extends StatelessWidget {
  const BreakdownBar({
    super.key,
    required this.left,
    required this.right,
    required this.leftColor,
    required this.rightColor,
  });

  final int left;
  final int right;
  final Color leftColor;
  final Color rightColor;

  @override
  Widget build(BuildContext context) {
    final total = left + right;
    return ClipRRect(
      borderRadius: BorderRadius.circular(ZxRadius.pill),
      child: SizedBox(
        height: ZxSize.breakdownBarHeight,
        width: double.infinity,
        child: total == 0
            ? ColoredBox(color: context.zx.palette.glassStrong)
            : Row(
                crossAxisAlignment: CrossAxisAlignment.stretch, // segments fill the bar's height
                children: [
                  if (left > 0)
                    Expanded(
                      flex: left,
                      child: ColoredBox(color: leftColor),
                    ),
                  if (right > 0)
                    Expanded(
                      flex: right,
                      child: ColoredBox(color: rightColor),
                    ),
                ],
              ),
      ),
    );
  }
}

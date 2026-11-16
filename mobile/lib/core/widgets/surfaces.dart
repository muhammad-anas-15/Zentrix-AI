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
    final dir = Directionality.of(context);
    return DecoratedBox(
      decoration: BoxDecoration(
        color: p.background,
        gradient: RadialGradient(
          center: AlignmentDirectional.topStart.resolve(dir),
          radius: ZxEffects.glowRadius,
          colors: [p.glowPrimary, p.glowPrimary.withValues(alpha: 0)],
        ),
      ),
      child: DecoratedBox(
        decoration: BoxDecoration(
          gradient: RadialGradient(
            center: AlignmentDirectional.bottomEnd.resolve(dir),
            radius: ZxEffects.glowRadius,
            colors: [p.glowSecondary, p.glowSecondary.withValues(alpha: 0)],
          ),
        ),
        child: child,
      ),
    );
  }
}

/// The Zentrix mark: a "Z" on the accent gradient with a soft glow.
class BrandMark extends StatelessWidget {
  const BrandMark({super.key, this.size = ZxSize.brandMark});

  final double size;

  @override
  Widget build(BuildContext context) {
    final zx = context.zx;
    final p = zx.palette;
    return Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        gradient: LinearGradient(begin: Alignment.topLeft, end: Alignment.bottomRight, colors: [p.accent, p.accentAlt]),
        borderRadius: BorderRadius.circular(size * 0.3),
        boxShadow: [BoxShadow(color: p.accent.withValues(alpha: 0.45), blurRadius: size * 0.6)],
      ),
      child: Text(
        'Z',
        style: (size > ZxSize.brandMark ? zx.text.display : zx.text.title).copyWith(
          color: p.textOnAccent,
          height: 1,
          fontWeight: ZxType.bold,
        ),
      ),
    );
  }
}

/// Frosted surface (backdrop blur) for floating bars. Only floating surfaces blur, to keep scrolling smooth.
class FrostedBar extends StatelessWidget {
  const FrostedBar({super.key, required this.child, this.edge = AxisDirection.down});

  final Widget child;

  /// Which edge carries the hairline (down = app bar, up = bottom navigation).
  final AxisDirection edge;

  @override
  Widget build(BuildContext context) {
    final p = context.zx.palette;
    final line = BorderSide(color: p.glassBorder, width: ZxSize.hairline);
    return ClipRect(
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: ZxEffects.glassBlur, sigmaY: ZxEffects.glassBlur),
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: p.glassFloating,
            border: edge == AxisDirection.down ? Border(bottom: line) : Border(top: line),
          ),
          child: child,
        ),
      ),
    );
  }
}

/// App bar that floats over the content with a frosted background.
class GlassAppBar extends StatelessWidget implements PreferredSizeWidget {
  const GlassAppBar({super.key, required this.title, this.actions, this.bottom, this.leading});

  final String title;
  final List<Widget>? actions;
  final PreferredSizeWidget? bottom;
  final Widget? leading;

  @override
  Size get preferredSize => Size.fromHeight(kToolbarHeight + (bottom?.preferredSize.height ?? 0));

  @override
  Widget build(BuildContext context) => AppBar(
    title: Text(title),
    actions: actions,
    bottom: bottom,
    leading: leading,
    flexibleSpace: const FrostedBar(child: SizedBox.expand()),
  );
}

/// Standard scrolling page: frosted app bar, glow background, centred content column with token spacing.
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
    final bar = title == null ? null : GlassAppBar(title: title!, actions: actions, bottom: bottom, leading: leading);
    final top = bar == null ? ZxSpace.sm : MediaQuery.paddingOf(context).top + bar.preferredSize.height + ZxSpace.sm;
    Widget list = ListView.separated(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: EdgeInsets.fromLTRB(ZxSpace.gutter, top, ZxSpace.gutter, ZxSpace.navClearance),
      itemCount: children.length,
      separatorBuilder: (_, _) => const SizedBox(height: ZxSpace.md),
      itemBuilder: (_, i) => children[i],
    );
    if (onRefresh != null) {
      list = RefreshIndicator(edgeOffset: top - ZxSpace.sm, onRefresh: onRefresh!, child: list);
    }
    return Scaffold(
      extendBodyBehindAppBar: bar != null,
      appBar: bar,
      floatingActionButton: floatingActionButton,
      body: ZxBackground(
        child: SafeArea(
          top: bar == null,
          bottom: false,
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

/// Translucent "glass" card with depth.
///
/// * [level]: base (flat), raised (default: gradient fill, light edge, soft shadow), floating.
/// * [accent]: emphasised border and a soft glow in that colour (selection, important state).
/// * [tint]: a faint wash of a semantic colour (e.g. the condition of the market shown inside).
class GlassCard extends StatelessWidget {
  const GlassCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(ZxSpace.lg),
    this.onTap,
    this.accent,
    this.tint,
    this.level = ZxLevel.raised,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;
  final VoidCallback? onTap;
  final Color? accent;
  final Color? tint;
  final ZxLevel level;

  @override
  Widget build(BuildContext context) {
    final p = context.zx.palette;
    final dir = Directionality.of(context);
    final radius = BorderRadius.circular(ZxRadius.lg);
    final top = switch (level) {
      ZxLevel.base => p.glass,
      ZxLevel.raised => p.glassStrong,
      ZxLevel.floating => p.glassFloating,
    };
    final washed = tint == null ? top : Color.alphaBlend(tint!.withValues(alpha: ZxEffects.stateTint), top);
    final shadows = <BoxShadow>[
      if (level != ZxLevel.base)
        BoxShadow(
          color: p.shadow,
          blurRadius: level == ZxLevel.floating ? ZxEffects.floatingShadowBlur : ZxEffects.raisedShadowBlur,
          offset: Offset(0, level == ZxLevel.floating ? ZxEffects.floatingShadowOffset : ZxEffects.raisedShadowOffset),
          spreadRadius: -ZxSpace.md,
        ),
      if (accent != null) BoxShadow(color: accent!.withValues(alpha: 0.16), blurRadius: ZxEffects.glowBlur),
    ];
    Widget body = DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: radius,
        boxShadow: shadows,
        gradient: LinearGradient(
          begin: AlignmentDirectional.topStart.resolve(dir),
          end: AlignmentDirectional.bottomEnd.resolve(dir),
          colors: [washed, p.glass],
        ),
      ),
      child: CustomPaint(
        foregroundPainter: _EdgePainter(
          radius: ZxRadius.lg,
          top: accent?.withValues(alpha: ZxEffects.accentBorder) ?? p.highlight,
          bottom: accent?.withValues(alpha: ZxEffects.accentBorder * 0.4) ?? p.glassBorder,
        ),
        // a transparent Material above the gradient: list tiles and buttons inside show their ink ripples
        child: Material(
          type: MaterialType.transparency,
          borderRadius: radius,
          clipBehavior: Clip.antiAlias,
          child: Padding(padding: padding, child: child),
        ),
      ),
    );
    if (onTap != null) {
      body = Material(
        type: MaterialType.transparency,
        child: InkWell(borderRadius: radius, onTap: onTap, child: body),
      );
    }
    return body;
  }
}

/// A 1px border that catches the light at the top and fades towards the bottom.
class _EdgePainter extends CustomPainter {
  _EdgePainter({required this.radius, required this.top, required this.bottom});

  final double radius;
  final Color top;
  final Color bottom;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = ZxSize.hairline
      ..shader = LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [top, bottom, bottom],
        stops: const [0, 0.45, 1],
      ).createShader(rect);
    canvas.drawRRect(RRect.fromRectAndRadius(rect.deflate(ZxSize.hairline / 2), Radius.circular(radius)), paint);
  }

  @override
  bool shouldRepaint(_EdgePainter old) => old.top != top || old.bottom != bottom || old.radius != radius;
}

class SectionHeader extends StatelessWidget {
  const SectionHeader(this.title, {super.key, this.trailing, this.caption});

  final String title;
  final Widget? trailing;
  final String? caption;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: ZxSpace.md),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: context.zx.text.title),
              if (caption != null) Text(caption!, style: context.zx.text.caption),
            ],
          ),
        ),
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
          Flexible(
            child: Text(
              label,
              style: context.zx.text.label.copyWith(color: color),
              overflow: TextOverflow.ellipsis,
            ),
          ),
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

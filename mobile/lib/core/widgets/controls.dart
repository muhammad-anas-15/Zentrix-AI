import 'package:flutter/material.dart';

import '../format/formatters.dart';
import '../theme/theme.dart';
import '../theme/tokens.dart';

/// Pill-shaped segmented control with a sliding, glowing indicator.
class ZxSegmented<T> extends StatelessWidget {
  const ZxSegmented({super.key, required this.segments, required this.selected, this.onChanged});

  /// (value, label) pairs, in display order.
  final List<(T, String)> segments;
  final T selected;
  final ValueChanged<T>? onChanged;

  @override
  Widget build(BuildContext context) {
    final zx = context.zx;
    final p = zx.palette;
    final n = segments.length;
    final index = segments.indexWhere((s) => s.$1 == selected);
    return Container(
      height: ZxSize.segmentHeight,
      decoration: BoxDecoration(
        color: p.glass,
        borderRadius: BorderRadius.circular(ZxRadius.pill),
        border: Border.all(color: p.glassBorder, width: ZxSize.hairline),
      ),
      child: Stack(
        children: [
          if (index >= 0)
            AnimatedAlign(
              duration: ZxMotion.normal,
              curve: ZxMotion.emphasized,
              alignment: AlignmentDirectional(n == 1 ? 0 : -1 + 2 * index / (n - 1), 0),
              child: FractionallySizedBox(
                widthFactor: 1 / n,
                heightFactor: 1,
                child: Padding(
                  padding: const EdgeInsets.all(ZxSpace.xxs + 1),
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      gradient: p.accentGradient,
                      borderRadius: BorderRadius.circular(ZxRadius.pill),
                      boxShadow: [BoxShadow(color: p.accent.withValues(alpha: 0.35), blurRadius: ZxEffects.glowBlur)],
                    ),
                  ),
                ),
              ),
            ),
          Row(
            children: [
              for (final (value, label) in segments)
                Expanded(
                  child: Semantics(
                    button: true,
                    selected: value == selected,
                    child: InkWell(
                      borderRadius: BorderRadius.circular(ZxRadius.pill),
                      onTap: onChanged == null ? null : () => onChanged!(value),
                      child: Center(
                        child: AnimatedDefaultTextStyle(
                          duration: ZxMotion.fast,
                          style: zx.text.label.copyWith(color: value == selected ? p.textOnAccent : p.textSecondary),
                          child: Text(label, maxLines: 1, overflow: TextOverflow.ellipsis),
                        ),
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

/// A horizontally scrolling row of filter chips; the selected one carries the accent gradient.
class ZxChipBar<T> extends StatelessWidget {
  const ZxChipBar({super.key, required this.chips, required this.selected, required this.onChanged});

  /// (value, label, optional icon), in display order.
  final List<(T, String, IconData?)> chips;
  final T selected;
  final ValueChanged<T> onChanged;

  @override
  Widget build(BuildContext context) {
    final zx = context.zx;
    final p = zx.palette;
    return SizedBox(
      height: ZxSize.segmentHeight,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: chips.length,
        separatorBuilder: (_, _) => const SizedBox(width: ZxSpace.sm),
        itemBuilder: (context, i) {
          final (value, label, icon) = chips[i];
          final on = value == selected;
          final fg = on ? p.textOnAccent : p.textSecondary;
          return Semantics(
            button: true,
            selected: on,
            child: AnimatedContainer(
              duration: ZxMotion.normal,
              curve: ZxMotion.emphasized,
              decoration: BoxDecoration(
                gradient: on ? p.accentGradient : null,
                color: on ? null : p.glass,
                borderRadius: BorderRadius.circular(ZxRadius.pill),
                border: Border.all(color: on ? p.accent : p.glassBorder, width: ZxSize.hairline),
                boxShadow: on ? [BoxShadow(color: p.accent.withValues(alpha: 0.3), blurRadius: ZxEffects.glowBlur)] : null,
              ),
              child: Material(
                type: MaterialType.transparency,
                child: InkWell(
                  borderRadius: BorderRadius.circular(ZxRadius.pill),
                  onTap: () => onChanged(value),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: ZxSpace.lg),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        if (icon != null) ...[
                          Icon(icon, size: ZxSize.iconSm, color: fg),
                          const SizedBox(width: ZxSpace.xs),
                        ],
                        Text(label, style: zx.text.label.copyWith(color: fg)),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}

/// Percent change in a soft pill with an arrow: green up, red down, grey when unknown.
class ChangePill extends StatelessWidget {
  const ChangePill({super.key, required this.pct, this.suffix});

  final double? pct;
  final String? suffix;

  @override
  Widget build(BuildContext context) {
    final zx = context.zx;
    final p = zx.palette;
    final v = pct;
    final (fg, bg, icon) = v == null
        ? (p.neutral, p.neutralSoft, Icons.remove)
        : v >= 0
        ? (p.bullish, p.bullishSoft, Icons.arrow_upward_rounded)
        : (p.bearish, p.bearishSoft, Icons.arrow_downward_rounded);
    return DecoratedBox(
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(ZxRadius.pill)),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: ZxSpace.sm, vertical: ZxSpace.xxs),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: ZxSize.iconXs, color: fg),
            const SizedBox(width: ZxSpace.xxs),
            Text(
              '${Fmt.signedPercent(v)}${suffix == null ? '' : ' $suffix'}',
              style: zx.text.label.copyWith(color: fg),
            ),
          ],
        ),
      ),
    );
  }
}

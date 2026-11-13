import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/format/formatters.dart';
import '../../../../core/l10n.dart';
import '../../../../core/theme/theme.dart';
import '../../../../core/theme/tokens.dart';
import '../../../../core/widgets/badges.dart';
import '../../../../core/widgets/states.dart';
import '../../../../core/widgets/surfaces.dart';
import '../../application/market_providers.dart';
import '../../domain/models.dart';

/// ATR stop-loss / take-profit with each target's historical base rate (Premium: trade_levels).
class LevelsCard extends ConsumerWidget {
  const LevelsCard({super.key, required this.symbol, required this.timeframe, required this.side, this.onSide});

  final String symbol;
  final String timeframe;
  final String side;
  final ValueChanged<String>? onSide;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final zx = context.zx;
    final key = (symbol: symbol, timeframe: timeframe, side: side);
    final value = ref.watch(levelsProvider(key));
    return GlassCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(child: Text(l.levelsTitle, style: zx.text.bodyStrong)),
              const PremiumBadge(),
            ],
          ),
          const SizedBox(height: ZxSpace.md),
          SegmentedButton<String>(
            segments: [
              ButtonSegment(value: 'long', label: Text(l.sideLong)),
              ButtonSegment(value: 'short', label: Text(l.sideShort)),
            ],
            selected: {side},
            showSelectedIcon: false,
            onSelectionChanged: onSide == null ? null : (s) => onSide!(s.first),
          ),
          const SizedBox(height: ZxSpace.md),
          AsyncValueView<Levels>(
            value: value,
            compact: true,
            onRetry: () => ref.invalidate(levelsProvider(key)),
            data: (lv) => _LevelsBody(levels: lv),
          ),
        ],
      ),
    );
  }
}

class _LevelsBody extends StatelessWidget {
  const _LevelsBody({required this.levels});

  final Levels levels;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final zx = context.zx;
    final d = levels.entry == null ? null : Fmt.guessDecimals(levels.entry!);
    Widget row(String label, double? price, Color color, {String? note}) => Padding(
      padding: const EdgeInsets.symmetric(vertical: ZxSpace.xs),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: ZxSpace.xs,
            height: ZxSpace.xxl,
            decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(ZxRadius.pill)),
          ),
          const SizedBox(width: ZxSpace.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: zx.text.label),
                if (note != null) Text(note, style: zx.text.caption),
              ],
            ),
          ),
          Text(Fmt.price(price, decimals: d), style: zx.text.metricSmall),
        ],
      ),
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        row(l.entry, levels.entry, zx.palette.accentAlt),
        row('${l.stop} (${Fmt.number(levels.slAtr, decimals: 1)} ATR)', levels.stop, zx.palette.bearish),
        for (final t in levels.targets)
          row(
            l.targetR(Fmt.number(t.r, decimals: t.r == t.r.roundToDouble() ? 0 : 1)),
            t.price,
            zx.palette.bullish,
            note: t.baseRate.hitRate == null
                ? l.baseRateUnknown
                : l.baseRate(Fmt.ratio(t.baseRate.hitRate), Fmt.ratio(t.baseRate.breakEvenHitRate)),
          ),
        for (final n in levels.notes) ...[const SizedBox(height: ZxSpace.xs), Text(n, style: zx.text.caption)],
        const SizedBox(height: ZxSpace.md),
        Disclaimer(text: l.levelsNote),
      ],
    );
  }
}

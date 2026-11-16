import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/format/formatters.dart';
import '../../../../core/l10n.dart';
import '../../../../core/theme/theme.dart';
import '../../../../core/theme/tokens.dart';
import '../../../../core/widgets/badges.dart';
import '../../../../core/widgets/charts.dart';
import '../../../../core/widgets/states.dart';
import '../../../../core/widgets/surfaces.dart';
import '../../application/market_providers.dart';
import '../../domain/models.dart';

/// Colour of a projection: the pattern's side only when history shows an edge, otherwise neutral.
Color projectionColor(BuildContext context, PatternOutlook o) {
  final p = context.zx.palette;
  final bias = o.pattern?.bias ?? 0;
  if (!o.hasEdge || bias == 0) return p.neutral;
  return bias > 0 ? p.bullish : p.bearish;
}

/// Technical Pattern Projection: the pattern now, the structure, what followed it before (base rate against any
/// candle), and the projected range. Never a prediction.
class PatternCard extends ConsumerWidget {
  const PatternCard({super.key, required this.symbol, required this.timeframe, this.decimals});

  final String symbol;
  final String timeframe;
  final int? decimals;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final zx = context.zx;
    final key = (symbol: symbol, timeframe: timeframe);
    return GlassCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(Icons.auto_graph_rounded, size: ZxSize.icon, color: zx.palette.accent),
              const SizedBox(width: ZxSpace.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(l.patternTitle, style: zx.text.bodyStrong),
                    Text(l.patternLabel, style: zx.text.caption),
                  ],
                ),
              ),
              const PremiumBadge(),
            ],
          ),
          const SizedBox(height: ZxSpace.md),
          AsyncValueView<PatternOutlook?>(
            value: ref.watch(patternProvider(key)),
            compact: true,
            onRetry: () => ref.invalidate(patternProvider(key)),
            data: (o) => o == null
                ? Text(l.noScenario, style: zx.text.secondary)
                : _Body(outlook: o, decimals: decimals ?? Fmt.guessDecimals(o.lastClose)),
          ),
        ],
      ),
    );
  }
}

class _Body extends StatelessWidget {
  const _Body({required this.outlook, required this.decimals});

  final PatternOutlook outlook;
  final int decimals;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final zx = context.zx;
    final p = zx.palette;
    final o = outlook;
    final pattern = o.pattern;
    final br = o.baseRate;
    final proj = o.projection;
    final color = projectionColor(context, o);
    final st = o.structure;
    final swing = switch (st.swing) {
      'uptrend' => l.swingUp,
      'downtrend' => l.swingDown,
      _ => l.swingRange,
    };
    final trend = switch (st.trendRegime) {
      'trending' => l.trendTrending,
      'weak trend' => l.trendWeak,
      'ranging' => l.trendRanging,
      _ => null,
    };
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (pattern == null)
          Text(l.noPatternNow, style: zx.text.secondary)
        else ...[
          Wrap(
            spacing: ZxSpace.sm,
            runSpacing: ZxSpace.xs,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Pill(
                label: pattern.name,
                color: color == p.neutral ? p.textPrimary : color,
                background: color.withValues(alpha: 0.16),
                icon: Icons.candlestick_chart_rounded,
              ),
              Pill(
                label: switch (pattern.bias) {
                  1 => l.classicBullish,
                  -1 => l.classicBearish,
                  _ => l.classicNeutral,
                },
                color: p.textSecondary,
                background: p.glass,
              ),
            ],
          ),
          const SizedBox(height: ZxSpace.sm),
          Text(pattern.meaning, style: zx.text.secondary),
          const SizedBox(height: ZxSpace.xs),
          Text(l.patternPastCases(pattern.pastCases), style: zx.text.caption),
        ],
        const SizedBox(height: ZxSpace.md),
        Wrap(
          spacing: ZxSpace.xs,
          runSpacing: ZxSpace.xs,
          children: [
            Pill(label: swing, color: p.accentAlt, background: p.accentSoft, icon: Icons.stacked_line_chart_rounded),
            if (trend != null)
              Pill(
                label: st.adx == null ? trend : '$trend · ADX ${Fmt.number(st.adx, decimals: 0)}',
                color: p.textSecondary,
                background: p.glass,
              ),
            if (st.rsi != null)
              Pill(label: 'RSI ${Fmt.number(st.rsi, decimals: 0)}', color: p.textSecondary, background: p.glass),
            if (st.momentumPct != null)
              Pill(
                label: l.momentumValue(Fmt.signedPercent(st.momentumPct)),
                color: p.textSecondary,
                background: p.glass,
              ),
          ],
        ),
        if (br != null && br.rate != null && pattern != null) ...[
          const Divider(height: ZxSpace.xxl),
          Text(
            l.patternBaseRate(
              pattern.bias > 0 ? l.higher : l.lower,
              br.horizon,
              Fmt.ratio(br.rate, decimals: 0),
              br.cases,
            ),
            style: zx.text.body,
          ),
          const SizedBox(height: ZxSpace.sm),
          CiBar(
            value: br.rate,
            low: br.ci95 != null && br.ci95!.length == 2 ? br.ci95![0] : null,
            high: br.ci95 != null && br.ci95!.length == 2 ? br.ci95![1] : null,
            reference: br.baseline ?? 0.5,
          ),
          const SizedBox(height: ZxSpace.xs),
          Text(l.patternBaseline(Fmt.ratio(br.baseline, decimals: 0)), style: zx.text.caption),
          const SizedBox(height: ZxSpace.sm),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(
                br.edge ? Icons.verified_outlined : Icons.warning_amber_rounded,
                size: ZxSize.iconSm,
                color: br.edge ? p.bullish : p.caution,
              ),
              const SizedBox(width: ZxSpace.sm),
              Expanded(
                child: Text(
                  br.edge ? l.patternEdge : l.patternNoEdge,
                  style: zx.text.caption.copyWith(color: p.textSecondary),
                ),
              ),
            ],
          ),
        ],
        if (proj != null && proj.steps.isNotEmpty) ...[
          const Divider(height: ZxSpace.xxl),
          Text(
            l.patternRange(
              proj.steps.length,
              Fmt.ltr(
                '${Fmt.price(proj.steps.last.bandLow, decimals: decimals)} – '
                '${Fmt.price(proj.steps.last.bandHigh, decimals: decimals)}',
              ),
            ),
            style: zx.text.body,
          ),
          if (proj.basis == 'all_candles') ...[
            const SizedBox(height: ZxSpace.xs),
            Text(
              pattern == null ? l.patternNoneRange : l.patternTypicalRange(pattern.pastCases),
              style: zx.text.caption,
            ),
          ],
        ],
        const SizedBox(height: ZxSpace.md),
        Disclaimer(text: l.patternDisclaimer),
      ],
    );
  }
}

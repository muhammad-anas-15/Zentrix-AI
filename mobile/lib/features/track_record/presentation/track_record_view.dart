import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/format/formatters.dart';
import '../../../core/l10n.dart';
import '../../../core/theme/theme.dart';
import '../../../core/theme/tokens.dart';
import '../../../core/widgets/badges.dart';
import '../../../core/widgets/states.dart';
import '../../../core/widgets/surfaces.dart';
import '../../market/domain/models.dart';
import '../data/track_record_repository.dart';
import '../domain/models.dart';

/// The public, live track record: counts and hit rates computed by the server from every stored signal.
class TrackRecordView extends ConsumerWidget {
  const TrackRecordView({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final zx = context.zx;
    return ListView(
      padding: const EdgeInsets.fromLTRB(ZxSpace.gutter, ZxSpace.lg, ZxSpace.gutter, ZxSpace.huge),
      children: [
        Text(l.trackRecordTitle, style: zx.text.headline),
        const SizedBox(height: ZxSpace.xs),
        Text(l.trackRecordIntro, style: zx.text.secondary),
        const SizedBox(height: ZxSpace.lg),
        AsyncValueView<TrackRecord>(
          value: ref.watch(trackRecordProvider),
          onRetry: () => ref.invalidate(trackRecordProvider),
          data: (tr) => Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _CountsCard(counts: tr.overall),
              const SizedBox(height: ZxSpace.md),
              if (tr.byStrength.isNotEmpty) ...[
                SectionHeader(l.byStrength),
                const SizedBox(height: ZxSpace.sm),
                GlassCard(
                  padding: EdgeInsets.zero,
                  child: Column(children: [for (final c in tr.byStrength) _StrengthRow(counts: c)]),
                ),
              ],
              if (tr.method != null) ...[const SizedBox(height: ZxSpace.md), Text(tr.method!, style: zx.text.caption)],
            ],
          ),
        ),
        const SizedBox(height: ZxSpace.lg),
        SectionHeader(l.recentSignals),
        const SizedBox(height: ZxSpace.sm),
        AsyncValueView<SignalPage>(
          value: ref.watch(recentResolvedSignalsProvider),
          compact: true,
          onRetry: () => ref.invalidate(recentResolvedSignalsProvider),
          data: (page) => page.items.isEmpty
              ? EmptyView(message: l.noSignals, icon: Icons.query_stats)
              : GlassCard(
                  padding: EdgeInsets.zero,
                  child: Column(children: [for (final s in page.items) _SignalRow(signal: s)]),
                ),
        ),
        const SizedBox(height: ZxSpace.lg),
        const Disclaimer(),
      ],
    );
  }
}

class _CountsCard extends StatelessWidget {
  const _CountsCard({required this.counts});

  final OutcomeCounts counts;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final zx = context.zx;
    final c = counts;
    final ci = c.ci95;
    return GlassCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          MetricGrid(
            tiles: [
              MetricTile(label: l.signalsTotal, value: '${c.signals}'),
              MetricTile(label: l.pending, value: '${c.pending}'),
              MetricTile(
                label: l.hitRate,
                value: Fmt.ratio(c.hitRate),
                caption: ci != null && ci.length == 2 && ci[0] != null && ci[1] != null
                    ? l.ci95(Fmt.ratio(ci[0]), Fmt.ratio(ci[1]))
                    : null,
              ),
              MetricTile(label: l.decided, value: '${c.decided}'),
            ],
          ),
          const SizedBox(height: ZxSpace.lg),
          Row(
            children: [
              Text('${l.wins} ${c.wins}', style: zx.text.label.copyWith(color: zx.palette.bullish)),
              const Spacer(),
              Text('${l.losses} ${c.losses}', style: zx.text.label.copyWith(color: zx.palette.bearish)),
            ],
          ),
          const SizedBox(height: ZxSpace.xs),
          BreakdownBar(left: c.wins, right: c.losses, leftColor: zx.palette.bullish, rightColor: zx.palette.bearish),
        ],
      ),
    );
  }
}

class _StrengthRow extends StatelessWidget {
  const _StrengthRow({required this.counts});

  final OutcomeCounts counts;

  @override
  Widget build(BuildContext context) {
    final zx = context.zx;
    return ListTile(
      title: Align(alignment: AlignmentDirectional.centerStart, child: StrengthBadge(counts.strength ?? '')),
      subtitle: Text('${context.l10n.decided} ${counts.decided} · ${context.l10n.wins} ${counts.wins}'),
      trailing: Text(Fmt.ratio(counts.hitRate), style: zx.text.metricSmall),
    );
  }
}

class _SignalRow extends StatelessWidget {
  const _SignalRow({required this.signal});

  final Signal signal;

  @override
  Widget build(BuildContext context) {
    final s = signal;
    final move = s.outcome?.movePct;
    return ListTile(
      title: Text('${s.symbol} · ${s.timeframe}', style: context.zx.text.bodyStrong),
      subtitle: Wrap(
        spacing: ZxSpace.xs,
        runSpacing: ZxSpace.xs,
        children: [
          DirectionChip(up: s.isUp, actionable: s.isActionable),
          StrengthBadge(s.strength),
        ],
      ),
      trailing: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          OutcomeChip(s.outcome?.outcome),
          if (move != null) Text(Fmt.signedPercent(move, decimals: 3), style: context.zx.text.caption),
        ],
      ),
    );
  }
}

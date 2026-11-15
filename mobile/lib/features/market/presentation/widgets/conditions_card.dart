import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/format/formatters.dart';
import '../../../../core/l10n.dart';
import '../../../../core/providers.dart';
import '../../../../core/theme/theme.dart';
import '../../../../core/theme/tokens.dart';
import '../../../../core/widgets/badges.dart';
import '../../../../core/widgets/states.dart';
import '../../../../core/widgets/surfaces.dart';
import '../../application/market_providers.dart';
import '../../domain/models.dart';

/// Market-condition light with each input and its reason.
class ConditionsCard extends ConsumerWidget {
  const ConditionsCard({super.key, required this.symbol, this.timeframe = defaultTimeframe});

  final String symbol;
  final String timeframe;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final key = (symbol: symbol, timeframe: timeframe);
    final value = ref.watch(conditionsProvider(key));
    final zx = context.zx;
    return GlassCard(
      accent: value.value == null ? null : ConditionLight.colorOf(context, value.value!.light),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(child: Text('${context.l10n.conditionsTitle} · $symbol', style: zx.text.label)),
              Text(timeframe, style: zx.text.caption),
            ],
          ),
          const SizedBox(height: ZxSpace.md),
          AsyncValueView<Conditions>(
            value: value,
            compact: true,
            onRetry: () => ref.invalidate(conditionsProvider(key)),
            data: (c) => Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                ConditionLight(c.light),
                const SizedBox(height: ZxSpace.md),
                for (final f in c.factors) _FactorRow(factor: f),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _FactorRow extends StatelessWidget {
  const _FactorRow({required this.factor});

  final ConditionFactor factor;

  @override
  Widget build(BuildContext context) {
    final zx = context.zx;
    final p = zx.palette;
    final color = switch (factor.status) {
      'ok' => p.bullish,
      'caution' => p.caution,
      'danger' => p.bearish,
      'info' => p.accentAlt,
      _ => p.neutral,
    };
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: ZxSpace.xs),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: ZxSpace.xs),
            child: Icon(Icons.circle, size: ZxSpace.sm, color: color),
          ),
          const SizedBox(width: ZxSpace.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(factorName(context, factor.name), style: zx.text.label.copyWith(color: p.textPrimary)),
                if (factor.detail.isNotEmpty) Text(factor.detail, style: zx.text.caption),
              ],
            ),
          ),
        ],
      ),
    );
  }

  static String factorName(BuildContext context, String name) {
    final l = context.l10n;
    return switch (name) {
      'market' => l.factorMarket,
      'data' => l.factorData,
      'trend' => l.factorTrend,
      'volatility' => l.factorVolatility,
      'session' => l.factorSession,
      'news' => l.factorNews,
      _ => name,
    };
  }
}

/// News guard: state and a live countdown to the next relevant event.
class NewsGuardCard extends ConsumerWidget {
  const NewsGuardCard({super.key, required this.symbol});

  final String symbol;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final value = ref.watch(newsGuardProvider(symbol));
    final zx = context.zx;
    final l = context.l10n;
    return GlassCard(
      child: AsyncValueView<NewsGuard>(
        value: value,
        compact: true,
        onRetry: () => ref.invalidate(newsGuardProvider(symbol)),
        data: (g) {
          final next = g.nextEvent;
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(child: Text(l.newsGuardTitle, style: zx.text.label)),
                  NewsStateChip(g.state),
                ],
              ),
              const SizedBox(height: ZxSpace.md),
              if (g.state == 'unknown')
                // a stale or missing calendar never reads as "nothing coming"
                Text(l.newsUnknownBody, style: zx.text.secondary.copyWith(color: zx.palette.caution))
              else if (next == null)
                Text(l.newsNoUpcoming, style: zx.text.secondary)
              else ...[
                Text(l.newsNextEvent('${next.currency} ${next.title}'), style: zx.text.bodyStrong),
                const SizedBox(height: ZxSpace.xs),
                _Countdown(eventAt: next.eventAt),
                Text(Fmt.dateTime(next.eventAt, context.localeCode), style: zx.text.caption),
              ],
            ],
          );
        },
      ),
    );
  }
}

class _Countdown extends ConsumerWidget {
  const _Countdown({required this.eventAt});

  final DateTime eventAt;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final now = ref.watch(secondTickerProvider).value ?? DateTime.now();
    final left = eventAt.difference(now).inSeconds;
    return Text(Fmt.countdown(left), style: context.zx.text.metric.copyWith(color: context.zx.palette.caution));
  }
}

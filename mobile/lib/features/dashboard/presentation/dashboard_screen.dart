import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/format/formatters.dart';
import '../../../core/l10n.dart';
import '../../../core/providers.dart';
import '../../../core/theme/theme.dart';
import '../../../core/theme/tokens.dart';
import '../../../core/widgets/badges.dart';
import '../../../core/widgets/charts.dart';
import '../../../core/widgets/controls.dart';
import '../../../core/widgets/motion.dart';
import '../../../core/widgets/states.dart';
import '../../../core/widgets/surfaces.dart';
import '../../alerts/data/alerts_repository.dart';
import '../../auth/application/session.dart';
import '../../market/application/market_providers.dart';
import '../../market/domain/models.dart';
import '../../market/presentation/markets_screen.dart';

/// Home: the Market Radar. When markets are worth attention, how far price may move, what event comes next.
/// It describes conditions and measured ranges; it never calls a direction.
class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final zx = context.zx;
    final user = ref.watch(currentUserProvider);
    final unread = ref.watch(inboxProvider).value?.unread ?? 0;
    final radar = ref.watch(radarProvider);
    return ZxPage(
      title: l.marketRadar,
      actions: [
        IconButton(
          tooltip: l.alerts,
          onPressed: () => context.push('/alerts'),
          icon: Badge(
            isLabelVisible: unread > 0,
            label: Text('$unread'),
            backgroundColor: zx.palette.bearish,
            child: const Icon(Icons.notifications_none_rounded),
          ),
        ),
      ],
      onRefresh: () async {
        ref
          ..invalidate(scenarioProvider)
          ..invalidate(inboxProvider);
        ref.invalidate(radarProvider);
        await ref.read(radarProvider.future);
      },
      children: [
        if (user == null) _GuestBanner(onSignIn: ref.read(sessionProvider.notifier).goToSignIn),
        AsyncValueView<Radar>(
          value: radar,
          onRetry: () => ref.invalidate(radarProvider),
          data: (r) => _RadarBody(radar: r),
        ),
        const FadeSlideIn(index: 8, child: _SignalsLabCard()),
        const Disclaimer(),
      ],
    );
  }
}

class _RadarBody extends ConsumerWidget {
  const _RadarBody({required this.radar});

  final Radar radar;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    if (radar.items.isEmpty) return EmptyView(message: l.noRadarData, icon: Icons.radar);
    final wanted = ref.watch(focusSymbolProvider);
    final focus = radar.items.firstWhere(
      (i) => i.symbol == wanted,
      orElse: () => radar.items.firstWhere((i) => i.hasData, orElse: () => radar.items.first),
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        FadeSlideIn(child: _HeroCard(item: focus)),
        const SizedBox(height: ZxSpace.md),
        FadeSlideIn(index: 1, child: _ExpectedRangeCard(item: focus)),
        const SizedBox(height: ZxSpace.md),
        FadeSlideIn(index: 2, child: _NextEventCard(item: focus)),
        SectionHeader(l.marketsNow, caption: l.radarRanking),
        const SizedBox(height: ZxSpace.sm),
        for (final (i, item) in radar.items.indexed)
          Padding(
            padding: const EdgeInsets.only(bottom: ZxSpace.sm),
            child: FadeSlideIn(
              index: i + 3,
              child: _RadarRow(
                item: item,
                selected: item.symbol == focus.symbol,
                onTap: () => ref.read(focusSymbolProvider.notifier).select(item.symbol),
              ),
            ),
          ),
      ],
    );
  }
}

Color _lightColor(BuildContext context, String light) => ConditionLight.colorOf(context, light);

/// Trend / volatility / news chips shared by the hero card and the radar rows.
List<Widget> _stateChips(BuildContext context, RadarItem item, {bool withNews = false}) {
  final l = context.l10n;
  final p = context.zx.palette;
  final chips = <Widget>[];
  final trend = switch (item.trendRegime) {
    'trending' => l.trendTrending,
    'weak trend' => l.trendWeak,
    'ranging' => l.trendRanging,
    _ => null,
  };
  if (trend != null) {
    chips.add(
      Pill(
        label: trend,
        color: item.trendRegime == 'trending' ? p.accentAlt : p.neutral,
        background: item.trendRegime == 'trending' ? p.accentSoft : p.neutralSoft,
        icon: item.trendRegime != 'trending'
            ? Icons.swap_horiz_rounded
            : (item.trendDirection == 'down' ? Icons.south_east_rounded : Icons.north_east_rounded),
      ),
    );
  }
  final (vol, volFg, volBg) = switch (item.volatilityRegime) {
    'low' => (l.volLow, p.neutral, p.neutralSoft),
    'normal' => (l.volNormal, p.accentAlt, p.accentSoft),
    'high' => (l.volHigh, p.caution, p.cautionSoft),
    'extreme' => (l.volExtreme, p.bearish, p.bearishSoft),
    _ => (null, p.neutral, p.neutralSoft),
  };
  if (vol != null) chips.add(Pill(label: vol, color: volFg, background: volBg, icon: Icons.ssid_chart_rounded));
  if (withNews || item.newsState != 'clear') chips.add(NewsStateChip(item.newsState));
  return chips;
}

class _HeroCard extends StatelessWidget {
  const _HeroCard({required this.item});

  final RadarItem item;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final zx = context.zx;
    final up = (item.change24hPct ?? 0) >= 0;
    return GlassCard(
      tint: _lightColor(context, item.light),
      padding: const EdgeInsets.fromLTRB(ZxSpace.xl, ZxSpace.xl, ZxSpace.xl, ZxSpace.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(item.symbol, style: zx.text.title),
                    Text(item.displayName, style: zx.text.caption),
                  ],
                ),
              ),
              ConditionLight(item.light),
            ],
          ),
          const SizedBox(height: ZxSpace.md),
          Wrap(
            crossAxisAlignment: WrapCrossAlignment.center,
            spacing: ZxSpace.md,
            runSpacing: ZxSpace.xs,
            children: [
              FlashOnChange(
                value: item.lastPrice,
                child: Text(Fmt.price(item.lastPrice, decimals: item.priceDecimals), style: zx.text.heroPrice),
              ),
              ChangePill(pct: item.change24hPct, suffix: l.change24h),
            ],
          ),
          if (item.lastCandleClose != null)
            Padding(
              padding: const EdgeInsets.only(top: ZxSpace.xs),
              child: Text(
                '${l.lastClose} · ${Fmt.dateTime(item.lastCandleClose!, context.localeCode)}',
                style: zx.text.caption,
              ),
            ),
          if (item.spark.length > 1) ...[
            const SizedBox(height: ZxSpace.md),
            SizedBox(
              height: ZxSize.heroChartHeight,
              child: AreaChart(values: item.spark, color: up ? zx.palette.bullish : zx.palette.bearish),
            ),
          ],
          const SizedBox(height: ZxSpace.md),
          Wrap(
            spacing: ZxSpace.sm,
            runSpacing: ZxSpace.sm,
            children: [
              ..._stateChips(context, item, withNews: true),
              for (final s in item.sessions)
                Pill(
                  label: s,
                  color: zx.palette.textSecondary,
                  background: zx.palette.glass,
                  icon: Icons.schedule_rounded,
                ),
            ],
          ),
          if (item.reasons.isNotEmpty) ...[
            const SizedBox(height: ZxSpace.md),
            for (final r in item.reasons.take(2))
              Padding(
                padding: const EdgeInsets.only(bottom: ZxSpace.xs),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(Icons.error_outline_rounded, size: ZxSize.iconSm, color: _lightColor(context, item.light)),
                    const SizedBox(width: ZxSpace.sm),
                    Expanded(
                      child: Text(r, style: zx.text.caption.copyWith(color: zx.palette.textSecondary)),
                    ),
                  ],
                ),
              ),
          ],
          Align(
            alignment: AlignmentDirectional.centerEnd,
            child: TextButton.icon(
              onPressed: () => context.push(pairLocation(item.symbol)),
              icon: const Icon(Icons.candlestick_chart_outlined, size: ZxSize.iconSm),
              label: Text(l.viewPair),
            ),
          ),
        ],
      ),
    );
  }
}

/// How far price may move over the next candles (scenario bands), shown with the coverage it really achieved.
class _ExpectedRangeCard extends ConsumerWidget {
  const _ExpectedRangeCard({required this.item});

  final RadarItem item;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final zx = context.zx;
    final key = (symbol: item.symbol, timeframe: defaultTimeframe);
    return GlassCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.unfold_more_rounded, size: ZxSize.icon, color: zx.palette.accent),
              const SizedBox(width: ZxSpace.sm),
              Expanded(child: Text(l.expectedRange, style: zx.text.bodyStrong)),
              const PremiumBadge(),
            ],
          ),
          const SizedBox(height: ZxSpace.md),
          AsyncValueView<Scenario?>(
            value: ref.watch(scenarioProvider(key)),
            compact: true,
            onRetry: () => ref.invalidate(scenarioProvider(key)),
            data: (s) {
              final steps = s?.steps.where((x) => x.low != null && x.high != null).toList() ?? const [];
              if (s == null || steps.isEmpty) return Text(l.noScenario, style: zx.text.secondary);
              final last = steps.last;
              final minutes = last.at.difference(s.asOf).inMinutes;
              final measured = last.coverage;
              // flag only a band that is statistically short: its whole 95% range lies below the target
              final ci = last.coverageCi95;
              final upper = ci != null && ci.length == 2 ? ci[1] : null;
              final short = upper != null
                  ? upper < last.nominalCoverage
                  : (measured ?? 1) < last.nominalCoverage - 0.05;
              return Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${Fmt.price(last.low, decimals: item.priceDecimals)} – '
                    '${Fmt.price(last.high, decimals: item.priceDecimals)}',
                    style: zx.text.price,
                  ),
                  Text(l.expectedRangeNext(steps.length, minutes), style: zx.text.caption),
                  const SizedBox(height: ZxSpace.md),
                  RangeFan(
                    lastClose: s.lastClose,
                    decimals: item.priceDecimals,
                    steps: [for (final x in steps) (low: x.low, median: x.median, high: x.high)],
                  ),
                  const SizedBox(height: ZxSpace.md),
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Icon(
                        short ? Icons.warning_amber_rounded : Icons.verified_outlined,
                        size: ZxSize.iconSm,
                        color: short ? zx.palette.caution : zx.palette.bullish,
                      ),
                      const SizedBox(width: ZxSpace.sm),
                      Expanded(
                        child: Text(
                          l.rangeCoverage(
                            Fmt.ratio(last.nominalCoverage, decimals: 0),
                            Fmt.ratio(measured, decimals: 0),
                            last.coverageTested,
                          ),
                          style: zx.text.caption.copyWith(color: zx.palette.textSecondary),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: ZxSpace.sm),
                  Disclaimer(text: l.rangeNotDirection),
                ],
              );
            },
          ),
        ],
      ),
    );
  }
}

class _NextEventCard extends ConsumerWidget {
  const _NextEventCard({required this.item});

  final RadarItem item;

  static const _window = Duration(hours: 2); // the news guard's caution lead for high impact

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final zx = context.zx;
    final p = zx.palette;
    final event = item.nextEvent;
    if (item.newsState == 'unknown' || event == null) {
      return GlassCard(
        level: ZxLevel.base,
        child: Row(
          children: [
            Expanded(
              child: Text(
                item.newsState == 'unknown' ? l.newsUnknownBody : l.newsNoUpcoming,
                style: zx.text.secondary.copyWith(color: item.newsState == 'unknown' ? p.caution : null),
              ),
            ),
            const SizedBox(width: ZxSpace.md),
            NewsStateChip(item.newsState),
          ],
        ),
      );
    }
    final now = ref.watch(secondTickerProvider).value ?? DateTime.now();
    final left = event.eventAt.difference(now);
    final color = switch (item.newsState) {
      'blackout' => p.bearish,
      'caution' => p.caution,
      _ => p.accentAlt,
    };
    return GlassCard(
      accent: item.newsState == 'blackout' ? p.bearish : null,
      child: Row(
        children: [
          CountdownRing(
            fraction: left.inSeconds / _window.inSeconds,
            color: color,
            child: Text(Fmt.countdown(left.inSeconds), style: zx.text.chartLabel.copyWith(color: p.textPrimary)),
          ),
          const SizedBox(width: ZxSpace.lg),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(l.nextEvent.toUpperCase(), style: zx.text.overline),
                const SizedBox(height: ZxSpace.xxs),
                Text('${event.currency} · ${event.title}', style: zx.text.bodyStrong),
                const SizedBox(height: ZxSpace.xs),
                Wrap(
                  spacing: ZxSpace.sm,
                  runSpacing: ZxSpace.xs,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    Pill(
                      label: event.impact == 'high' ? l.impactHigh : l.impactMedium,
                      color: event.impact == 'high' ? p.bearish : p.caution,
                      background: event.impact == 'high' ? p.bearishSoft : p.cautionSoft,
                    ),
                    Text(Fmt.dateTime(event.eventAt, context.localeCode), style: zx.text.caption),
                  ],
                ),
              ],
            ),
          ),
          NewsStateChip(item.newsState),
        ],
      ),
    );
  }
}

class _RadarRow extends StatelessWidget {
  const _RadarRow({required this.item, required this.selected, required this.onTap});

  final RadarItem item;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final zx = context.zx;
    final p = zx.palette;
    final change = item.change24hPct;
    final moveColor = change == null ? p.neutral : (change >= 0 ? p.bullish : p.bearish);
    return GlassCard(
      level: selected ? ZxLevel.raised : ZxLevel.base,
      accent: selected ? p.accent : null,
      padding: const EdgeInsets.fromLTRB(ZxSpace.md, ZxSpace.md, ZxSpace.xs, ZxSpace.md),
      onTap: onTap,
      child: Row(
        children: [
          StatusOrb(color: _lightColor(context, item.light), pulse: false),
          const SizedBox(width: ZxSpace.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(item.symbol, style: zx.text.bodyStrong),
                const SizedBox(height: ZxSpace.xs),
                if (item.hasData)
                  Wrap(spacing: ZxSpace.xs, runSpacing: ZxSpace.xs, children: _stateChips(context, item))
                else
                  Text(l.feedUnavailable, style: zx.text.caption),
              ],
            ),
          ),
          if (item.spark.length > 1) ...[
            const SizedBox(width: ZxSpace.sm),
            SizedBox(
              width: ZxSize.rowSparkWidth,
              height: ZxSize.rowSparkHeight,
              child: AreaChart(values: item.spark, color: moveColor, showLastDot: false),
            ),
          ],
          const SizedBox(width: ZxSpace.md),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              FlashOnChange(
                value: item.lastPrice,
                child: Text(Fmt.price(item.lastPrice, decimals: item.priceDecimals), style: zx.text.priceSmall),
              ),
              Text(Fmt.signedPercent(change), style: zx.text.caption.copyWith(color: moveColor)),
            ],
          ),
          IconButton(
            tooltip: l.viewPair,
            visualDensity: VisualDensity.compact,
            onPressed: () => context.push(pairLocation(item.symbol)),
            icon: Icon(Icons.chevron_right_rounded, color: p.textMuted),
          ),
        ],
      ),
    );
  }
}

/// Direction models live in the Lab until a strength tier proves itself on unseen data.
class _SignalsLabCard extends StatelessWidget {
  const _SignalsLabCard();

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final zx = context.zx;
    return GlassCard(
      level: ZxLevel.base,
      onTap: () => context.go('/journal?tab=2'),
      child: Row(
        children: [
          Icon(Icons.science_outlined, color: zx.palette.accentAlt),
          const SizedBox(width: ZxSpace.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(l.signalsLabTitle, style: zx.text.bodyStrong),
                const SizedBox(height: ZxSpace.xxs),
                Text(l.signalsLabBody, style: zx.text.caption),
              ],
            ),
          ),
          Icon(Icons.chevron_right_rounded, color: zx.palette.textMuted),
        ],
      ),
    );
  }
}

class _GuestBanner extends StatelessWidget {
  const _GuestBanner({required this.onSignIn});

  final VoidCallback onSignIn;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    return GlassCard(
      accent: context.zx.palette.accent,
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(l.guestMode, style: context.zx.text.bodyStrong),
                Text(l.guestModeBody, style: context.zx.text.caption),
              ],
            ),
          ),
          TextButton(onPressed: onSignIn, child: Text(l.signIn)),
        ],
      ),
    );
  }
}

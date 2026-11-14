import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/format/formatters.dart';
import '../../../core/l10n.dart';
import '../../../core/providers.dart';
import '../../../core/theme/theme.dart';
import '../../../core/theme/tokens.dart';
import '../../../core/widgets/charts.dart';
import '../../../core/widgets/controls.dart';
import '../../../core/widgets/motion.dart';
import '../../../core/widgets/states.dart';
import '../../../core/widgets/surfaces.dart';
import '../../market/domain/models.dart';
import '../../settings/presentation/profile_button.dart';
import '../application/pulse_providers.dart';
import '../domain/models.dart';
import 'news_widgets.dart';

/// Market Pulse: what is moving markets now. Scheduled events (economic calendar) and headlines from central
/// banks, regulators and market news, with impact tags and asset badges. Headlines open at their publisher.
class PulseScreen extends ConsumerWidget {
  const PulseScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final filter = ref.watch(pulseFilterProvider);
    final asset = ref.watch(pulseAssetProvider);
    return ZxPage(
      title: l.pulseTitle,
      actions: [
        IconButton(
          tooltip: l.pulseSources,
          onPressed: () => showModalBottomSheet<void>(
            context: context,
            isScrollControlled: true,
            builder: (_) => const _SourcesSheet(),
          ),
          icon: const Icon(Icons.info_outline_rounded),
        ),
        const ProfileButton(),
      ],
      onRefresh: () async {
        ref
          ..invalidate(pulseCalendarProvider)
          ..invalidate(pulseFeedProvider);
        await ref.read(pulseFeedProvider.future);
      },
      children: [
        const FadeSlideIn(child: _UpNextCard()),
        ZxChipBar<PulseFilter>(
          chips: [
            (PulseFilter.all, l.pulseFilterAll, null),
            (PulseFilter.high, l.pulseFilterHigh, Icons.bolt_rounded),
            (PulseFilter.centralBanks, l.pulseFilterCentralBanks, Icons.account_balance_outlined),
            (PulseFilter.crypto, l.assetCrypto, Icons.currency_bitcoin_rounded),
            (PulseFilter.fx, l.pulseFilterFx, Icons.public_rounded),
          ],
          selected: filter,
          onChanged: ref.read(pulseFilterProvider.notifier).select,
        ),
        if (asset != null)
          Row(
            children: [
              Text(l.pulseFilteredBy, style: context.zx.text.caption),
              const SizedBox(width: ZxSpace.sm),
              AssetBadge(asset, selected: true, onTap: () => ref.read(pulseAssetProvider.notifier).select(null)),
              const SizedBox(width: ZxSpace.xs),
              IconButton(
                visualDensity: VisualDensity.compact,
                tooltip: l.clearFilter,
                onPressed: () => ref.read(pulseAssetProvider.notifier).select(null),
                icon: const Icon(Icons.close_rounded, size: ZxSize.iconSm),
              ),
            ],
          ),
        AsyncValueView<NewsFeed>(
          value: ref.watch(pulseFeedProvider),
          onRetry: () => ref.invalidate(pulseFeedProvider),
          data: (feed) => _NewsList(feed: feed),
        ),
        Disclaimer(text: l.pulseNote),
      ],
    );
  }
}

class _NewsList extends ConsumerWidget {
  const _NewsList({required this.feed});

  final NewsFeed feed;

  static const _breakingS = 3600; // a high-impact headline from the last hour is pinned on top

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final zx = context.zx;
    final p = zx.palette;
    final asset = ref.watch(pulseAssetProvider);
    final limit = ref.watch(pulseLimitProvider);
    final ok = feed.sources.where((s) => s.ok).length;
    final updated = feed.updatedAt;
    final now = DateTime.now();
    final breaking = feed.items.where((i) => i.impact == 'high' && i.ageS < _breakingS).toList();
    final rest = feed.items.where((i) => !breaking.contains(i)).toList();
    void onAsset(String a) => ref.read(pulseAssetProvider.notifier).select(a);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            StatusOrb(color: ok == feed.sources.length ? p.bullish : p.caution, size: ZxSize.orb * 0.6),
            const SizedBox(width: ZxSpace.sm),
            Expanded(
              child: Text(
                [
                  if (updated != null)
                    l.pulseUpdated(
                      now.difference(updated).inSeconds < 60 ? l.justNow : Fmt.ago(now.difference(updated).inSeconds),
                    ),
                  l.pulseSourcesOk(ok, feed.sources.length),
                ].join(' · '),
                style: zx.text.caption,
              ),
            ),
          ],
        ),
        const SizedBox(height: ZxSpace.md),
        if (feed.items.isEmpty) EmptyView(message: l.noHeadlines, icon: Icons.newspaper_rounded),
        if (breaking.isNotEmpty) ...[
          Text(l.breaking.toUpperCase(), style: zx.text.overline.copyWith(color: p.bearish)),
          const SizedBox(height: ZxSpace.sm),
          for (final (i, item) in breaking.indexed)
            Padding(
              padding: const EdgeInsets.only(bottom: ZxSpace.sm),
              child: FadeSlideIn(
                index: i,
                child: NewsCard(item: item, highlight: true, selectedAsset: asset, onAsset: onAsset),
              ),
            ),
          const SizedBox(height: ZxSpace.sm),
        ],
        for (final (i, item) in rest.indexed)
          Padding(
            padding: const EdgeInsets.only(bottom: ZxSpace.sm),
            child: FadeSlideIn(
              index: (i + breaking.length).clamp(0, 10),
              child: NewsCard(item: item, selectedAsset: asset, onAsset: onAsset),
            ),
          ),
        if (feed.items.length >= limit && limit < PulseLimitNotifier.max)
          OutlinedButton(onPressed: ref.read(pulseLimitProvider.notifier).more, child: Text(l.loadMore)),
      ],
    );
  }
}

/// The next scheduled high-impact event with a countdown, and what else is on the calendar.
class _UpNextCard extends ConsumerWidget {
  const _UpNextCard();

  static const _window = Duration(hours: 2);

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final zx = context.zx;
    final p = zx.palette;
    return GlassCard(
      child: AsyncValueView<CalendarPage>(
        value: ref.watch(pulseCalendarProvider),
        compact: true,
        onRetry: () => ref.invalidate(pulseCalendarProvider),
        data: (cal) {
          final now = ref.watch(secondTickerProvider).value ?? DateTime.now();
          final upcoming = cal.items.where((e) => e.eventAt.isAfter(now)).toList();
          final next = upcoming.where((e) => e.impact == 'high').firstOrNull ?? upcoming.firstOrNull;
          final recent = cal.items.where((e) => !e.eventAt.isAfter(now)).toList().reversed.take(2);
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(Icons.event_note_rounded, size: ZxSize.icon, color: p.accent),
                  const SizedBox(width: ZxSpace.sm),
                  Expanded(child: Text(l.calendarTitle, style: zx.text.bodyStrong)),
                  if (cal.calendarUpdatedAt == null) Pill(label: l.newsStateUnknown, color: p.caution, background: p.cautionSoft),
                ],
              ),
              const SizedBox(height: ZxSpace.md),
              if (next == null)
                Text(l.newsNoUpcoming, style: zx.text.secondary)
              else
                Row(
                  children: [
                    CountdownRing(
                      fraction: next.eventAt.difference(now).inSeconds / _window.inSeconds,
                      color: next.impact == 'high' ? p.bearish : p.caution,
                      child: Text(
                        Fmt.countdown(next.eventAt.difference(now).inSeconds),
                        style: zx.text.chartLabel.copyWith(color: p.textPrimary),
                        textAlign: TextAlign.center,
                      ),
                    ),
                    const SizedBox(width: ZxSpace.lg),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(l.upNext.toUpperCase(), style: zx.text.overline),
                          const SizedBox(height: ZxSpace.xxs),
                          Text(next.title, style: zx.text.bodyStrong, maxLines: 2, overflow: TextOverflow.ellipsis),
                          const SizedBox(height: ZxSpace.xs),
                          Wrap(
                            spacing: ZxSpace.sm,
                            runSpacing: ZxSpace.xs,
                            crossAxisAlignment: WrapCrossAlignment.center,
                            children: [
                              AssetBadge(next.currency),
                              ImpactTag(next.impact),
                              Text(Fmt.dateTime(next.eventAt, context.localeCode), style: zx.text.caption),
                            ],
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              if (upcoming.length > 1 || recent.isNotEmpty) ...[
                const SizedBox(height: ZxSpace.md),
                const Divider(height: ZxSpace.lg),
                for (final e in [...recent.toList().reversed, ...upcoming.where((e) => e != next).take(4)])
                  _EventRow(event: e, past: !e.eventAt.isAfter(now)),
              ],
            ],
          );
        },
      ),
    );
  }
}

class _EventRow extends StatelessWidget {
  const _EventRow({required this.event, required this.past});

  final NewsEvent event;
  final bool past;

  @override
  Widget build(BuildContext context) {
    final zx = context.zx;
    final p = zx.palette;
    final l = context.l10n;
    final figures = [
      if (event.actual != null) '${l.actual} ${event.actual}',
      if (event.forecast != null) '${l.forecast} ${event.forecast}',
      if (event.previous != null) '${l.previous} ${event.previous}',
    ].join(' · ');
    return Opacity(
      opacity: past ? 0.6 : 1,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: ZxSpace.xs),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              width: ZxSize.rowSparkWidth,
              child: Text(Fmt.time(event.eventAt, context.localeCode), style: zx.text.priceSmall),
            ),
            Padding(
              padding: const EdgeInsets.only(top: ZxSpace.xs),
              child: Container(
                width: ZxSpace.sm,
                height: ZxSpace.sm,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: event.impact == 'high' ? p.bearish : p.caution,
                ),
              ),
            ),
            const SizedBox(width: ZxSpace.sm),
            AssetBadge(event.currency),
            const SizedBox(width: ZxSpace.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(event.title, style: zx.text.body, maxLines: 2, overflow: TextOverflow.ellipsis),
                  if (figures.isNotEmpty) Text(Fmt.ltr(figures), style: zx.text.caption),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Where the Pulse comes from, how impact tags are set, and which feeds are working.
class _SourcesSheet extends ConsumerWidget {
  const _SourcesSheet();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final zx = context.zx;
    final p = zx.palette;
    final feed = ref.watch(pulseFeedProvider).value;
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(ZxSpace.gutter, 0, ZxSpace.gutter, ZxSpace.xxl),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(l.pulseMethodTitle, style: zx.text.title),
            const SizedBox(height: ZxSpace.sm),
            Text(l.pulseMethod, style: zx.text.secondary),
            const SizedBox(height: ZxSpace.md),
            Text(l.pulseCoverage, style: zx.text.caption),
            const SizedBox(height: ZxSpace.lg),
            Text(l.pulseSources, style: zx.text.bodyStrong),
            const SizedBox(height: ZxSpace.sm),
            for (final s in feed?.sources ?? const <NewsSource>[])
              Padding(
                padding: const EdgeInsets.symmetric(vertical: ZxSpace.xs),
                child: Row(
                  children: [
                    Icon(newsKindIcon(s.kind), size: ZxSize.iconSm, color: p.textMuted),
                    const SizedBox(width: ZxSpace.sm),
                    Expanded(child: Text(s.name, style: zx.text.body)),
                    StatusOrb(color: s.ok ? p.bullish : p.caution, size: ZxSize.orb * 0.6, pulse: false),
                    const SizedBox(width: ZxSpace.sm),
                    Text(s.ok ? l.sourceOk : l.sourceDown, style: zx.text.caption),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}

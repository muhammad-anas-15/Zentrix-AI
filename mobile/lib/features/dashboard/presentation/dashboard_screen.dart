import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/format/formatters.dart';
import '../../../core/l10n.dart';
import '../../../core/theme/theme.dart';
import '../../../core/theme/tokens.dart';
import '../../../core/widgets/badges.dart';
import '../../../core/widgets/states.dart';
import '../../../core/widgets/surfaces.dart';
import '../../alerts/data/alerts_repository.dart';
import '../../alerts/domain/models.dart';
import '../../auth/application/session.dart';
import '../../market/application/market_providers.dart';
import '../../market/domain/models.dart';
import '../../market/presentation/markets_screen.dart';
import '../../market/presentation/widgets/conditions_card.dart';
import '../../market/presentation/widgets/signal_card.dart';
import 'widgets/sparkline.dart';

/// Home: market-condition light, news countdown, latest signal and a quick watchlist.
class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final zx = context.zx;
    final focus = ref.watch(focusSymbolProvider);
    final user = ref.watch(currentUserProvider);
    final unread = ref.watch(inboxProvider).value?.unread ?? 0;
    final signalKey = (symbol: focus, timeframe: defaultTimeframe);
    final signal = ref.watch(latestSignalProvider(signalKey));

    return ZxPage(
      title: l.marketOverview,
      actions: [
        IconButton(
          tooltip: l.alerts,
          onPressed: () => context.push('/alerts'),
          icon: Badge(
            isLabelVisible: unread > 0,
            label: Text('$unread'),
            backgroundColor: zx.palette.bearish,
            child: const Icon(Icons.notifications_none),
          ),
        ),
      ],
      onRefresh: () async {
        ref
          ..invalidate(conditionsProvider(signalKey))
          ..invalidate(newsGuardProvider(focus))
          ..invalidate(latestSignalProvider(signalKey))
          ..invalidate(watchlistsProvider)
          ..invalidate(inboxProvider);
        for (final s in defaultSymbols) {
          ref.invalidate(miniQuoteProvider(s));
        }
      },
      children: [
        if (user == null) _GuestBanner(onSignIn: ref.read(sessionProvider.notifier).goToSignIn),
        const _TickerStrip(),
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(
            children: [
              for (final s in defaultSymbols)
                Padding(
                  padding: const EdgeInsetsDirectional.only(end: ZxSpace.sm),
                  child: ChoiceChip(
                    label: Text(s),
                    selected: s == focus,
                    onSelected: (_) => ref.read(focusSymbolProvider.notifier).select(s),
                  ),
                ),
            ],
          ),
        ),
        ConditionsCard(symbol: focus),
        NewsGuardCard(symbol: focus),
        SectionHeader(
          l.latestSignal,
          trailing: TextButton(onPressed: () => context.push(pairLocation(focus)), child: Text(l.viewPair)),
        ),
        AsyncValueView<Signal?>(
          value: signal,
          compact: true,
          onRetry: () => ref.invalidate(latestSignalProvider(signalKey)),
          data: (s) => s == null
              ? GlassCard(child: Text(l.noSignalYet, style: zx.text.secondary))
              : SignalCard(signal: s, onTap: () => context.push(pairLocation(focus))),
        ),
        if (user != null) const _WatchlistSection(),
        const Disclaimer(),
      ],
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

/// Default markets with last close, ~24h change and a sparkline (from stored 15m candles).
class _TickerStrip extends ConsumerWidget {
  const _TickerStrip();

  @override
  Widget build(BuildContext context, WidgetRef ref) => SingleChildScrollView(
    scrollDirection: Axis.horizontal,
    child: Row(
      children: [
        for (final s in defaultSymbols)
          Padding(
            padding: const EdgeInsetsDirectional.only(end: ZxSpace.md),
            child: _TickerTile(symbol: s),
          ),
      ],
    ),
  );
}

class _TickerTile extends ConsumerWidget {
  const _TickerTile({required this.symbol});

  final String symbol;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final zx = context.zx;
    final q = ref.watch(miniQuoteProvider(symbol)).value;
    final change = q?.change24hPct;
    final color = change == null ? zx.palette.neutral : (change >= 0 ? zx.palette.bullish : zx.palette.bearish);
    return SizedBox(
      width: ZxSize.tickerWidth,
      child: GlassCard(
        padding: const EdgeInsets.all(ZxSpace.md),
        onTap: () => context.push(pairLocation(symbol)),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(symbol, style: zx.text.label),
            const SizedBox(height: ZxSpace.xs),
            Text(Fmt.price(q?.price), style: zx.text.metricSmall),
            Text(
              '${context.l10n.change24h} ${Fmt.signedPercent(change)}',
              style: zx.text.caption.copyWith(color: color),
            ),
            const SizedBox(height: ZxSpace.sm),
            SizedBox(
              height: ZxSize.sparkHeight,
              child: Sparkline(values: q?.spark ?? const [], color: color),
            ),
          ],
        ),
      ),
    );
  }
}

/// The user's first watchlist with quotes; offers to create one from the default markets.
class _WatchlistSection extends ConsumerWidget {
  const _WatchlistSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final lists = ref.watch(watchlistsProvider);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SectionHeader(l.watchlistTitle),
        const SizedBox(height: ZxSpace.sm),
        AsyncValueView<List<Watchlist>>(
          value: lists,
          compact: true,
          onRetry: () => ref.invalidate(watchlistsProvider),
          data: (ws) {
            if (ws.isEmpty) {
              return OutlinedButton.icon(
                icon: const Icon(Icons.add),
                label: Text(l.createWatchlist),
                onPressed: () async {
                  await ref.read(alertsRepositoryProvider).createWatchlist(l.watchlistTitle, defaultSymbols);
                  ref.invalidate(watchlistsProvider);
                },
              );
            }
            return _QuotesList(watchlistId: ws.first.id);
          },
        ),
      ],
    );
  }
}

class _QuotesList extends ConsumerWidget {
  const _QuotesList({required this.watchlistId});

  final int watchlistId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final zx = context.zx;
    return AsyncValueView<Quotes>(
      value: ref.watch(quotesProvider(watchlistId)),
      compact: true,
      onRetry: () => ref.invalidate(quotesProvider(watchlistId)),
      data: (q) => GlassCard(
        padding: EdgeInsets.zero,
        child: Column(
          children: [
            for (final item in q.items)
              ListTile(
                onTap: () => context.push(pairLocation(item.symbol)),
                title: Text(item.symbol, style: zx.text.bodyStrong),
                subtitle: Row(
                  children: [
                    NewsStateChip(item.newsState),
                    if (item.latestSignal != null) ...[
                      const SizedBox(width: ZxSpace.xs),
                      Flexible(child: StrengthBadge(item.latestSignal!.strength)),
                    ],
                  ],
                ),
                trailing: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(Fmt.price(item.price), style: zx.text.metricSmall),
                    Text(
                      Fmt.signedPercent(item.change24hPct),
                      style: zx.text.caption.copyWith(
                        color: (item.change24hPct ?? 0) >= 0 ? zx.palette.bullish : zx.palette.bearish,
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}

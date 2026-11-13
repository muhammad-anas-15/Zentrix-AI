import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/format/formatters.dart';
import '../../../core/l10n.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/theme/theme.dart';
import '../../../core/theme/tokens.dart';
import '../../../core/widgets/badges.dart';
import '../../../core/widgets/states.dart';
import '../../../core/widgets/surfaces.dart';
import '../../auth/application/session.dart';
import '../../auth/presentation/sign_in_prompt.dart';
import '../../track_record/presentation/track_record_view.dart';
import '../data/journal_repository.dart';
import '../domain/models.dart';

/// Journal (trades + stats, Premium) and the public track record.
class JournalScreen extends ConsumerWidget {
  const JournalScreen({super.key, this.initialTab = 0});

  final int initialTab;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final signedIn = ref.watch(currentUserProvider) != null;
    return DefaultTabController(
      length: 3,
      initialIndex: initialTab,
      child: Scaffold(
        appBar: AppBar(
          title: Text(l.journalTitle),
          bottom: TabBar(
            tabs: [
              Tab(text: l.tabTrades),
              Tab(text: l.tabStats),
              Tab(text: l.tabTrackRecord),
            ],
          ),
        ),
        floatingActionButton: signedIn
            ? FloatingActionButton.extended(
                key: const Key('addTrade'),
                onPressed: () => context.push('/journal/new'),
                icon: const Icon(Icons.add),
                label: Text(l.addTrade),
              )
            : null,
        body: ZxBackground(
          child: TabBarView(
            children: [
              signedIn ? const _TradesTab() : const _Padded(child: SignInPrompt()),
              signedIn ? const _StatsTab() : const _Padded(child: SignInPrompt()),
              const TrackRecordView(),
            ],
          ),
        ),
      ),
    );
  }
}

class _Padded extends StatelessWidget {
  const _Padded({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) => ListView(padding: const EdgeInsets.all(ZxSpace.gutter), children: [child]);
}

class _TradesTab extends ConsumerWidget {
  const _TradesTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    return RefreshIndicator(
      onRefresh: () => ref.refresh(journalProvider.future),
      child: ListView(
        padding: const EdgeInsets.fromLTRB(ZxSpace.gutter, ZxSpace.lg, ZxSpace.gutter, ZxSpace.huge * 2),
        children: [
          AsyncValueView<JournalPage>(
            value: ref.watch(journalProvider),
            onRetry: () => ref.invalidate(journalProvider),
            data: (page) => page.items.isEmpty
                ? EmptyView(message: l.noTrades, icon: Icons.menu_book_outlined)
                : Column(
                    children: [
                      for (final e in page.items)
                        Padding(
                          padding: const EdgeInsets.only(bottom: ZxSpace.md),
                          child: _TradeCard(entry: e),
                        ),
                    ],
                  ),
          ),
        ],
      ),
    );
  }
}

class _TradeCard extends ConsumerWidget {
  const _TradeCard({required this.entry});

  final JournalEntry entry;

  Future<void> _close(BuildContext context, WidgetRef ref) async {
    final price = await showModalBottomSheet<double>(
      context: context,
      isScrollControlled: true,
      builder: (_) => _CloseTradeSheet(entry: entry),
    );
    if (price == null || !context.mounted) return;
    await _guard(context, () async {
      await ref.read(journalRepositoryProvider).close(entry.id, exitPrice: price, exitAt: DateTime.now());
      ref.invalidate(journalProvider);
    });
  }

  Future<void> _delete(BuildContext context, WidgetRef ref) async {
    final l = context.l10n;
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: Text(l.deleteTradeConfirm),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: Text(l.cancel)),
          TextButton(onPressed: () => Navigator.pop(c, true), child: Text(l.delete)),
        ],
      ),
    );
    if (ok != true || !context.mounted) return;
    await _guard(context, () async {
      await ref.read(journalRepositoryProvider).delete(entry.id);
      ref.invalidate(journalProvider);
    });
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final zx = context.zx;
    final e = entry;
    final pnl = e.pnlAccount;
    final pnlColor = pnl == null ? zx.palette.textSecondary : (pnl >= 0 ? zx.palette.bullish : zx.palette.bearish);
    final d = Fmt.guessDecimals(e.entryPrice);
    return GlassCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(e.symbol, style: zx.text.bodyStrong),
              const SizedBox(width: ZxSpace.sm),
              Pill(
                label: e.side == 'long' ? l.sideLong : l.sideShort,
                color: e.side == 'long' ? zx.palette.bullish : zx.palette.bearish,
                background: e.side == 'long' ? zx.palette.bullishSoft : zx.palette.bearishSoft,
              ),
              const Spacer(),
              Pill(
                label: e.isOpen ? l.tradeOpen : l.tradeClosed,
                color: e.isOpen ? zx.palette.accent : zx.palette.neutral,
                background: e.isOpen ? zx.palette.accentSoft : zx.palette.neutralSoft,
              ),
              PopupMenuButton<String>(
                onSelected: (v) => v == 'delete' ? _delete(context, ref) : _close(context, ref),
                itemBuilder: (_) => [
                  if (e.isOpen) PopupMenuItem(value: 'close', child: Text(l.closeTrade)),
                  PopupMenuItem(value: 'delete', child: Text(l.delete)),
                ],
              ),
            ],
          ),
          const SizedBox(height: ZxSpace.sm),
          Text(
            '${Fmt.number(e.quantity, decimals: 0)} @ ${Fmt.price(e.entryPrice, decimals: d)}'
            '${e.exitPrice != null ? ' → ${Fmt.price(e.exitPrice, decimals: d)}' : ''}',
            style: zx.text.secondary,
          ),
          Text(Fmt.dateTime(e.entryAt, context.localeCode), style: zx.text.caption),
          if (!e.isOpen) ...[
            const SizedBox(height: ZxSpace.sm),
            Row(
              children: [
                Text(
                  Fmt.money(pnl, e.accountCurrency, signed: true),
                  style: zx.text.metricSmall.copyWith(color: pnlColor),
                ),
                const SizedBox(width: ZxSpace.md),
                if (e.rMultiple != null) Text('${Fmt.number(e.rMultiple, decimals: 2)} R', style: zx.text.label),
              ],
            ),
          ],
          for (final n in e.calcNotes) Text(n, style: zx.text.caption),
        ],
      ),
    );
  }
}

class _CloseTradeSheet extends StatefulWidget {
  const _CloseTradeSheet({required this.entry});

  final JournalEntry entry;

  @override
  State<_CloseTradeSheet> createState() => _CloseTradeSheetState();
}

class _CloseTradeSheetState extends State<_CloseTradeSheet> {
  final _price = TextEditingController();

  @override
  void dispose() {
    _price.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    return Padding(
      padding: EdgeInsets.fromLTRB(
        ZxSpace.gutter,
        0,
        ZxSpace.gutter,
        MediaQuery.viewInsetsOf(context).bottom + ZxSpace.xxl,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('${l.closeTrade} · ${widget.entry.symbol}', style: context.zx.text.title),
          const SizedBox(height: ZxSpace.lg),
          TextField(
            controller: _price,
            autofocus: true,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'[0-9.]'))],
            decoration: InputDecoration(labelText: l.exitPrice),
          ),
          const SizedBox(height: ZxSpace.lg),
          FilledButton(
            onPressed: () {
              final v = double.tryParse(_price.text);
              if (v != null && v > 0) Navigator.pop(context, v);
            },
            child: Text(l.save),
          ),
        ],
      ),
    );
  }
}

class _StatsTab extends ConsumerWidget {
  const _StatsTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final zx = context.zx;
    return RefreshIndicator(
      onRefresh: () => ref.refresh(journalStatsProvider.future),
      child: ListView(
        padding: const EdgeInsets.fromLTRB(ZxSpace.gutter, ZxSpace.lg, ZxSpace.gutter, ZxSpace.huge),
        children: [
          AsyncValueView<JournalStats>(
            value: ref.watch(journalStatsProvider),
            onRetry: () => ref.invalidate(journalStatsProvider),
            data: (s) {
              final cur = s.accountCurrency;
              return Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Row(
                    children: [
                      Expanded(child: Text(l.tabStats, style: zx.text.headline)),
                      const PremiumBadge(),
                    ],
                  ),
                  const SizedBox(height: ZxSpace.lg),
                  GlassCard(
                    child: MetricGrid(
                      tiles: [
                        MetricTile(
                          label: l.statsNetPnl,
                          value: Fmt.money(s.netPnl, cur, signed: true),
                          valueColor: s.netPnl >= 0 ? zx.palette.bullish : zx.palette.bearish,
                        ),
                        MetricTile(label: l.statsWinRate, value: Fmt.ratio(s.winRate)),
                        MetricTile(label: l.statsProfitFactor, value: Fmt.number(s.profitFactor)),
                        MetricTile(label: l.statsExpectancy, value: Fmt.money(s.expectancy, cur, signed: true)),
                        MetricTile(label: l.statsAvgR, value: Fmt.number(s.avgR)),
                        MetricTile(label: l.statsWorstStreak, value: '${s.maxConsecutiveLosses}'),
                        MetricTile(label: l.statsTrades, value: '${s.closed}'),
                      ],
                    ),
                  ),
                  const SizedBox(height: ZxSpace.md),
                  GlassCard(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Row(
                          children: [
                            Text('${l.wins} ${s.wins}', style: zx.text.label.copyWith(color: zx.palette.bullish)),
                            const Spacer(),
                            Text('${l.breakeven} ${s.breakeven}', style: zx.text.label),
                            const Spacer(),
                            Text('${l.losses} ${s.losses}', style: zx.text.label.copyWith(color: zx.palette.bearish)),
                          ],
                        ),
                        const SizedBox(height: ZxSpace.sm),
                        BreakdownBar(
                          left: s.wins,
                          right: s.losses,
                          leftColor: zx.palette.bullish,
                          rightColor: zx.palette.bearish,
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: ZxSpace.md),
                  Disclaimer(text: l.statsNote),
                ],
              );
            },
          ),
        ],
      ),
    );
  }
}

/// Runs an action and shows its error (if any) in a snackbar.
Future<void> _guard(BuildContext context, Future<void> Function() action) async {
  try {
    await action();
  } on ApiException catch (e) {
    if (!context.mounted) return;
    final l = context.l10n;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.isNetwork ? l.errorNetwork : e.message)));
  }
}

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

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
import '../../market/application/market_providers.dart';
import '../data/alerts_repository.dart';
import '../domain/models.dart';

/// Alert inbox and the user's alerts (price level, news, signal).
class AlertsScreen extends ConsumerWidget {
  const AlertsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final signedIn = ref.watch(currentUserProvider) != null;
    if (!signedIn) {
      return ZxPage(title: l.alertsTitle, children: const [SignInPrompt()]);
    }
    return DefaultTabController(
      length: 2,
      child: Scaffold(
        appBar: AppBar(
          title: Text(l.alertsTitle),
          bottom: TabBar(
            tabs: [
              Tab(text: l.tabInbox),
              Tab(text: l.tabMyAlerts),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () async {
                await ref.read(alertsRepositoryProvider).markAllRead();
                ref.invalidate(inboxProvider);
              },
              child: Text(l.markAllRead),
            ),
          ],
        ),
        floatingActionButton: FloatingActionButton.extended(
          onPressed: () => showModalBottomSheet<void>(
            context: context,
            isScrollControlled: true,
            builder: (_) => const _NewAlertSheet(),
          ),
          icon: const Icon(Icons.add_alert_outlined),
          label: Text(l.newAlert),
        ),
        body: const ZxBackground(child: TabBarView(children: [_InboxTab(), _AlertsTab()])),
      ),
    );
  }
}

class _InboxTab extends ConsumerWidget {
  const _InboxTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final zx = context.zx;
    return RefreshIndicator(
      onRefresh: () => ref.refresh(inboxProvider.future),
      child: ListView(
        padding: const EdgeInsets.fromLTRB(ZxSpace.gutter, ZxSpace.lg, ZxSpace.gutter, ZxSpace.huge * 2),
        children: [
          Disclaimer(text: l.pushNotConfigured),
          const SizedBox(height: ZxSpace.md),
          AsyncValueView<AlertInbox>(
            value: ref.watch(inboxProvider),
            onRetry: () => ref.invalidate(inboxProvider),
            data: (inbox) => inbox.items.isEmpty
                ? EmptyView(message: l.noAlertEvents, icon: Icons.notifications_none)
                : Column(
                    children: [
                      for (final e in inbox.items)
                        Padding(
                          padding: const EdgeInsets.only(bottom: ZxSpace.sm),
                          child: GlassCard(
                            accent: e.unread ? zx.palette.accent : null,
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(e.title, style: zx.text.bodyStrong),
                                const SizedBox(height: ZxSpace.xs),
                                Text(e.body, style: zx.text.secondary),
                                const SizedBox(height: ZxSpace.xs),
                                Text(Fmt.dateTime(e.triggeredAt, context.localeCode), style: zx.text.caption),
                              ],
                            ),
                          ),
                        ),
                    ],
                  ),
          ),
        ],
      ),
    );
  }
}

class _AlertsTab extends ConsumerWidget {
  const _AlertsTab();

  String _describe(AppLocalizations l, Alert a) => switch (a.kind) {
    'price_cross' =>
      '${a.symbol} ${a.params['direction'] == 'above' ? l.alertAbove : l.alertBelow} '
          '${Fmt.price((a.params['level'] as num?)?.toDouble())}',
    'news' => '${l.alertKindNews} · ${a.symbol ?? l.watchlistTitle} · ${a.params['lead_minutes']} min',
    'signal' =>
      '${l.alertKindSignal} · ${a.symbol ?? l.watchlistTitle} · '
          '${strengthLabel(l, '${a.params['min_strength']}')}+',
    _ => '${a.kind} ${a.symbol ?? ''}',
  };

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final zx = context.zx;
    final repo = ref.read(alertsRepositoryProvider);
    return RefreshIndicator(
      onRefresh: () => ref.refresh(alertsProvider.future),
      child: ListView(
        padding: const EdgeInsets.fromLTRB(ZxSpace.gutter, ZxSpace.lg, ZxSpace.gutter, ZxSpace.huge * 2),
        children: [
          AsyncValueView<List<Alert>>(
            value: ref.watch(alertsProvider),
            onRetry: () => ref.invalidate(alertsProvider),
            data: (alerts) => alerts.isEmpty
                ? EmptyView(message: l.noAlerts, icon: Icons.add_alert_outlined)
                : GlassCard(
                    padding: EdgeInsets.zero,
                    child: Column(
                      children: [
                        for (final a in alerts)
                          ListTile(
                            title: Text(_describe(l, a), style: zx.text.body),
                            subtitle: a.premium == null
                                ? null
                                : const Align(alignment: AlignmentDirectional.centerStart, child: PremiumBadge()),
                            leading: IconButton(
                              icon: const Icon(Icons.delete_outline),
                              onPressed: () async {
                                await repo.delete(a.id);
                                ref.invalidate(alertsProvider);
                              },
                            ),
                            trailing: Switch(
                              value: a.active,
                              onChanged: (v) async {
                                try {
                                  await repo.setActive(a.id, active: v);
                                } on ApiException catch (e) {
                                  if (context.mounted) {
                                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
                                  }
                                }
                                ref.invalidate(alertsProvider);
                              },
                            ),
                          ),
                      ],
                    ),
                  ),
          ),
        ],
      ),
    );
  }
}

class _NewAlertSheet extends ConsumerStatefulWidget {
  const _NewAlertSheet();

  @override
  ConsumerState<_NewAlertSheet> createState() => _NewAlertSheetState();
}

class _NewAlertSheetState extends ConsumerState<_NewAlertSheet> {
  String _kind = 'price_cross';
  String _symbol = defaultSymbols.first;
  String _direction = 'above';
  String _minStrength = 'Good';
  final _level = TextEditingController();
  final _lead = TextEditingController(text: '30');
  bool _saving = false;

  @override
  void dispose() {
    _level.dispose();
    _lead.dispose();
    super.dispose();
  }

  Future<void> _create() async {
    final l = context.l10n;
    final body = <String, Object?>{
      'kind': _kind,
      'symbol': _symbol,
      'params': switch (_kind) {
        'price_cross' => {'level': double.tryParse(_level.text) ?? 0, 'direction': _direction},
        'news' => {'lead_minutes': int.tryParse(_lead.text) ?? 30, 'min_impact': 'high'},
        _ => {'min_strength': _minStrength},
      },
      if (_kind == 'price_cross') 'timeframe': '15m',
    };
    setState(() => _saving = true);
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ref.read(alertsRepositoryProvider).create(body);
      ref.invalidate(alertsProvider);
      messenger.showSnackBar(SnackBar(content: Text(l.alertCreated)));
      if (mounted) Navigator.pop(context);
    } on ApiException catch (e) {
      messenger.showSnackBar(SnackBar(content: Text(e.isNetwork ? l.errorNetwork : e.message)));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
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
          Text(l.newAlert, style: context.zx.text.title),
          const SizedBox(height: ZxSpace.lg),
          SegmentedButton<String>(
            segments: [
              ButtonSegment(value: 'price_cross', label: Text(l.alertKindPrice)),
              ButtonSegment(value: 'news', label: Text(l.alertKindNews)),
              ButtonSegment(value: 'signal', label: Text(l.alertKindSignal)),
            ],
            selected: {_kind},
            showSelectedIcon: false,
            onSelectionChanged: (s) => setState(() => _kind = s.first),
          ),
          if (_kind == 'signal') ...[
            const SizedBox(height: ZxSpace.sm),
            const Align(alignment: AlignmentDirectional.centerStart, child: PremiumBadge()),
          ],
          const SizedBox(height: ZxSpace.md),
          DropdownButtonFormField<String>(
            initialValue: _symbol,
            decoration: InputDecoration(labelText: l.symbol),
            items: [for (final s in defaultSymbols) DropdownMenuItem(value: s, child: Text(s))],
            onChanged: (v) => setState(() => _symbol = v ?? _symbol),
          ),
          const SizedBox(height: ZxSpace.md),
          if (_kind == 'price_cross') ...[
            SegmentedButton<String>(
              segments: [
                ButtonSegment(value: 'above', label: Text(l.alertAbove)),
                ButtonSegment(value: 'below', label: Text(l.alertBelow)),
              ],
              selected: {_direction},
              showSelectedIcon: false,
              onSelectionChanged: (s) => setState(() => _direction = s.first),
            ),
            const SizedBox(height: ZxSpace.md),
            TextField(
              controller: _level,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'[0-9.]'))],
              decoration: InputDecoration(labelText: l.alertLevel),
            ),
          ] else if (_kind == 'news')
            TextField(
              controller: _lead,
              keyboardType: TextInputType.number,
              inputFormatters: [FilteringTextInputFormatter.digitsOnly],
              decoration: InputDecoration(labelText: l.alertLeadMinutes),
            )
          else
            DropdownButtonFormField<String>(
              initialValue: _minStrength,
              decoration: InputDecoration(labelText: l.alertMinStrength),
              items: [
                for (final s in ['Strong', 'Good', 'Moderate', 'Weak'])
                  DropdownMenuItem(value: s, child: Text(strengthLabel(l, s))),
              ],
              onChanged: (v) => setState(() => _minStrength = v ?? _minStrength),
            ),
          const SizedBox(height: ZxSpace.lg),
          FilledButton(onPressed: _saving ? null : _create, child: Text(l.save)),
        ],
      ),
    );
  }
}

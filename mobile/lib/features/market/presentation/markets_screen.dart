import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/l10n.dart';
import '../../../core/theme/theme.dart';
import '../../../core/theme/tokens.dart';
import '../../../core/widgets/states.dart';
import '../../../core/widgets/surfaces.dart';
import '../application/market_providers.dart';
import '../domain/models.dart';

/// All instruments by asset class, with search.
class MarketsScreen extends ConsumerStatefulWidget {
  const MarketsScreen({super.key});

  @override
  ConsumerState<MarketsScreen> createState() => _MarketsScreenState();
}

class _MarketsScreenState extends ConsumerState<MarketsScreen> {
  String _query = '';

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final value = ref.watch(instrumentsProvider);
    return ZxPage(
      title: l.marketsTitle,
      onRefresh: () async => ref.refresh(instrumentsProvider.future),
      children: [
        TextField(
          decoration: InputDecoration(prefixIcon: const Icon(Icons.search), hintText: l.searchMarkets),
          onChanged: (v) => setState(() => _query = v.trim().toLowerCase()),
        ),
        AsyncValueView<List<Instrument>>(
          value: value,
          onRetry: () => ref.invalidate(instrumentsProvider),
          data: (items) {
            final filtered = items
                .where(
                  (i) =>
                      _query.isEmpty ||
                      i.symbol.toLowerCase().contains(_query) ||
                      i.displayName.toLowerCase().contains(_query),
                )
                .toList();
            final groups = <String, List<Instrument>>{};
            for (final i in filtered) {
              groups.putIfAbsent(i.assetClass, () => []).add(i);
            }
            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                for (final cls in ['fx', 'metal', 'commodity', 'crypto', 'index', 'equity'])
                  if (groups[cls] != null) ...[
                    SectionHeader(_className(l, cls)),
                    const SizedBox(height: ZxSpace.sm),
                    GlassCard(
                      padding: EdgeInsets.zero,
                      child: Column(children: [for (final i in groups[cls]!) _InstrumentTile(instrument: i)]),
                    ),
                    const SizedBox(height: ZxSpace.md),
                  ],
              ],
            );
          },
        ),
      ],
    );
  }

  static String _className(AppLocalizations l, String cls) => switch (cls) {
    'fx' => l.assetFx,
    'metal' => l.assetMetal,
    'commodity' => l.assetCommodity,
    'crypto' => l.assetCrypto,
    _ => l.assetOther,
  };
}

class _InstrumentTile extends StatelessWidget {
  const _InstrumentTile({required this.instrument});

  final Instrument instrument;

  @override
  Widget build(BuildContext context) {
    final zx = context.zx;
    final live = instrument.hasLiveFeed;
    return ListTile(
      enabled: live,
      title: Text(instrument.symbol, style: zx.text.bodyStrong),
      subtitle: Text(live ? instrument.displayName : context.l10n.feedUnavailable),
      trailing: Icon(Icons.chevron_right, color: zx.palette.textMuted),
      onTap: live ? () => context.push(pairLocation(instrument.symbol)) : null,
    );
  }
}

/// Route of the pair view (symbols contain '/', so they travel as a query parameter).
String pairLocation(String symbol, {String? timeframe}) =>
    Uri(path: '/pair', queryParameters: {'symbol': symbol, 'tf': ?timeframe}).toString();

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/format/formatters.dart';
import '../../../core/l10n.dart';
import '../../../core/theme/theme.dart';
import '../../../core/theme/tokens.dart';
import '../../../core/widgets/badges.dart';
import '../../../core/widgets/charts.dart';
import '../../../core/widgets/controls.dart';
import '../../../core/widgets/motion.dart';
import '../../../core/widgets/states.dart';
import '../../../core/widgets/surfaces.dart';
import '../../settings/presentation/profile_button.dart';
import '../application/market_providers.dart';
import '../domain/models.dart';

const _classes = ['fx', 'metal', 'commodity', 'crypto', 'index', 'equity'];

/// All instruments by asset class, with search, prices and 24h moves (from the Radar) where data is stored.
class MarketsScreen extends ConsumerStatefulWidget {
  const MarketsScreen({super.key});

  @override
  ConsumerState<MarketsScreen> createState() => _MarketsScreenState();
}

class _MarketsScreenState extends ConsumerState<MarketsScreen> {
  String _query = '';
  String _class = 'all';

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final value = ref.watch(instrumentsProvider);
    final quotes = {for (final i in ref.watch(radarProvider).value?.items ?? const <RadarItem>[]) i.symbol: i};
    return ZxPage(
      title: l.marketsTitle,
      actions: const [ProfileButton()],
      onRefresh: () async {
        ref
          ..invalidate(instrumentsProvider)
          ..invalidate(radarProvider);
        await ref.read(instrumentsProvider.future);
      },
      children: [
        TextField(
          decoration: InputDecoration(prefixIcon: const Icon(Icons.search_rounded), hintText: l.searchMarkets),
          onChanged: (v) => setState(() => _query = v.trim().toLowerCase()),
        ),
        ZxChipBar<String>(
          chips: [
            ('all', l.pulseFilterAll, null),
            ('fx', l.assetFx, null),
            ('metal', l.assetMetal, null),
            ('commodity', l.assetCommodity, null),
            ('crypto', l.assetCrypto, null),
          ],
          selected: _class,
          onChanged: (v) => setState(() => _class = v),
        ),
        AsyncValueView<List<Instrument>>(
          value: value,
          onRetry: () => ref.invalidate(instrumentsProvider),
          data: (items) {
            final filtered = items
                .where(
                  (i) =>
                      (_class == 'all' || i.assetClass == _class) &&
                      (_query.isEmpty ||
                          i.symbol.toLowerCase().contains(_query) ||
                          i.displayName.toLowerCase().contains(_query)),
                )
                .toList();
            final groups = <String, List<Instrument>>{};
            for (final i in filtered) {
              groups.putIfAbsent(i.assetClass, () => []).add(i);
            }
            if (groups.isEmpty) return EmptyView(message: l.noMarketsMatch, icon: Icons.search_off_rounded);
            var row = 0;
            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                for (final cls in _classes)
                  if (groups[cls] != null) ...[
                    SectionHeader(
                      _className(l, cls),
                      trailing: Text('${groups[cls]!.length}', style: context.zx.text.caption),
                    ),
                    const SizedBox(height: ZxSpace.sm),
                    GlassCard(
                      level: ZxLevel.base,
                      padding: const EdgeInsets.symmetric(vertical: ZxSpace.xs),
                      child: Column(
                        children: [
                          for (final (i, inst) in groups[cls]!.indexed) ...[
                            if (i > 0)
                              const Divider(height: ZxSize.hairline, indent: ZxSpace.lg, endIndent: ZxSpace.lg),
                            FadeSlideIn(
                              index: (row++).clamp(0, 12),
                              child: _InstrumentRow(instrument: inst, quote: quotes[inst.symbol]),
                            ),
                          ],
                        ],
                      ),
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

class _InstrumentRow extends StatelessWidget {
  const _InstrumentRow({required this.instrument, required this.quote});

  final Instrument instrument;
  final RadarItem? quote;

  @override
  Widget build(BuildContext context) {
    final zx = context.zx;
    final p = zx.palette;
    final live = instrument.hasChartData;
    final dailyOnly = instrument.timeframes.length == 1 && instrument.timeframes.first == '1d';
    final q = quote;
    final change = q?.change24hPct;
    final moveColor = change == null ? p.neutral : (change >= 0 ? p.bullish : p.bearish);
    return Opacity(
      opacity: live ? 1 : 0.55,
      child: InkWell(
        onTap: live ? () => context.push(pairLocation(instrument.symbol)) : null,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: ZxSpace.lg, vertical: ZxSpace.md),
          child: Row(
            children: [
              StatusOrb(color: ConditionLight.colorOf(context, q?.light ?? 'unknown'), pulse: false),
              const SizedBox(width: ZxSpace.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(instrument.symbol, style: zx.text.bodyStrong, maxLines: 1, overflow: TextOverflow.ellipsis),
                    Text(
                      !live
                          ? context.l10n.feedUnavailable
                          : dailyOnly
                          ? '${instrument.displayName} · ${context.l10n.dailyOnlyShort}'
                          : instrument.displayName,
                      style: zx.text.caption,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
              if (q != null && q.spark.length > 1) ...[
                SizedBox(
                  width: ZxSize.rowSparkWidth,
                  height: ZxSize.rowSparkHeight,
                  child: AreaChart(values: q.spark, color: moveColor, showLastDot: false),
                ),
                const SizedBox(width: ZxSpace.md),
              ],
              if (q != null && q.hasData)
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(Fmt.price(q.lastPrice, decimals: q.priceDecimals), style: zx.text.priceSmall),
                    Text(Fmt.signedPercent(change), style: zx.text.caption.copyWith(color: moveColor)),
                  ],
                )
              else if (live)
                Icon(Icons.chevron_right_rounded, color: p.textMuted),
            ],
          ),
        ),
      ),
    );
  }
}

/// Route of the pair view (symbols contain '/', so they travel as a query parameter).
String pairLocation(String symbol, {String? timeframe}) =>
    Uri(path: '/pair', queryParameters: {'symbol': symbol, 'tf': ?timeframe}).toString();

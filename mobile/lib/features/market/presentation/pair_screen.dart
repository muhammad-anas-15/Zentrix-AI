import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/format/formatters.dart';
import '../../../core/l10n.dart';
import '../../../core/theme/theme.dart';
import '../../../core/theme/tokens.dart';
import '../../../core/widgets/controls.dart';
import '../../../core/widgets/states.dart';
import '../../../core/widgets/surfaces.dart';
import '../application/market_providers.dart';
import '../domain/models.dart';
import 'widgets/candle_chart.dart';
import 'widgets/conditions_card.dart';
import 'widgets/levels_card.dart';
import 'widgets/signal_card.dart';

/// One market: candles, the live signal, ATR levels, conditions and news.
class PairScreen extends ConsumerStatefulWidget {
  const PairScreen({super.key, required this.symbol, this.initialTimeframe = defaultTimeframe});

  final String symbol;
  final String initialTimeframe;

  @override
  ConsumerState<PairScreen> createState() => _PairScreenState();
}

class _PairScreenState extends ConsumerState<PairScreen> {
  late String _tf = widget.initialTimeframe;
  String? _side; // null = follow the signal's direction

  Future<void> _refresh() async {
    final k = (symbol: widget.symbol, timeframe: _tf);
    ref
      ..invalidate(candlesProvider(k))
      ..invalidate(latestSignalProvider(k))
      ..invalidate(conditionsProvider(k))
      ..invalidate(newsGuardProvider(widget.symbol));
    await ref.read(candlesProvider(k).future);
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final zx = context.zx;
    final key = (symbol: widget.symbol, timeframe: _tf);
    final candles = ref.watch(candlesProvider(key));
    final signal = ref.watch(latestSignalProvider(key));
    final instrument = ref.watch(instrumentProvider(widget.symbol));
    final decimals = instrument?.priceDecimals;
    final side = _side ?? (signal.value?.isUp == false ? 'short' : 'long');

    return ZxPage(
      title: widget.symbol,
      onRefresh: _refresh,
      children: [
        _PriceHeader(series: candles.value, decimals: decimals, name: instrument?.displayName),
        ZxSegmented<String>(
          segments: [for (final tf in chartTimeframes) (tf, tf)],
          selected: _tf,
          onChanged: (v) => setState(() => _tf = v),
        ),
        GlassCard(
          padding: const EdgeInsets.all(ZxSpace.sm),
          child: AsyncValueView<CandleSeries>(
            value: candles,
            onRetry: () => ref.invalidate(candlesProvider(key)),
            data: (s) => CandleChart(candles: s.candles, decimals: decimals),
          ),
        ),
        SectionHeader(l.latestSignal),
        AsyncValueView<Signal?>(
          value: signal,
          compact: true,
          onRetry: () => ref.invalidate(latestSignalProvider(key)),
          data: (s) =>
              s == null ? GlassCard(child: Text(l.noSignalYet, style: zx.text.secondary)) : SignalCard(signal: s),
        ),
        LevelsCard(symbol: widget.symbol, timeframe: _tf, side: side, onSide: (s) => setState(() => _side = s)),
        ConditionsCard(symbol: widget.symbol, timeframe: _tf),
        NewsGuardCard(symbol: widget.symbol),
        const Disclaimer(),
      ],
    );
  }
}

class _PriceHeader extends StatelessWidget {
  const _PriceHeader({required this.series, required this.decimals, this.name});

  final CandleSeries? series;
  final int? decimals;
  final String? name;

  @override
  Widget build(BuildContext context) {
    final zx = context.zx;
    final l = context.l10n;
    final candles = series?.candles ?? const <Candle>[];
    final last = candles.isEmpty ? null : candles.last;
    final change = last == null ? null : change24h(candles);
    final color = (change ?? 0) >= 0 ? zx.palette.bullish : zx.palette.bearish;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (name != null) Text(name!, style: zx.text.caption),
        Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Text(Fmt.price(last?.c, decimals: decimals), style: zx.text.price),
            const SizedBox(width: ZxSpace.md),
            if (change != null)
              Padding(
                padding: const EdgeInsets.only(bottom: ZxSpace.xs),
                child: Text(
                  '${Fmt.signedPercent(change)} ${l.change24h}',
                  style: zx.text.bodyStrong.copyWith(color: color),
                ),
              ),
          ],
        ),
        if (last != null) Text('${l.lastClose} · ${Fmt.dateTime(last.t, context.localeCode)}', style: zx.text.caption),
      ],
    );
  }
}

/// Percent change of the last close against the close ~24h earlier, from the loaded candles
/// (null when they do not reach back 24h).
double? change24h(List<Candle> candles) {
  if (candles.length < 2) return null;
  final last = candles.last;
  final cutoff = last.t.subtract(const Duration(hours: 24));
  Candle? ref;
  for (final c in candles) {
    if (c.t.isAfter(cutoff)) break;
    ref = c;
  }
  if (ref == null || ref.c == 0) return null;
  return (last.c / ref.c - 1) * 100;
}

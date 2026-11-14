import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/format/formatters.dart';
import '../../../core/l10n.dart';
import '../../../core/theme/theme.dart';
import '../../../core/theme/tokens.dart';
import '../../../core/widgets/controls.dart';
import '../../../core/widgets/motion.dart';
import '../../../core/widgets/states.dart';
import '../../../core/widgets/surfaces.dart';
import '../application/market_providers.dart';
import '../domain/models.dart';
import 'widgets/candle_chart.dart';
import 'widgets/conditions_card.dart';
import 'widgets/levels_card.dart';
import 'widgets/signal_card.dart';

enum PairTab { signal, levels, conditions, news }

/// One market, chart first: a live price header, the live chart, then the signal, ATR levels (drawn on the chart
/// while their tab is open), conditions and news.
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
  PairTab _tab = PairTab.signal;

  Future<void> _refresh() async {
    final k = (symbol: widget.symbol, timeframe: _tf);
    ref
      ..invalidate(candlesProvider(k))
      ..invalidate(liveCandleProvider(k))
      ..invalidate(latestSignalProvider(k))
      ..invalidate(conditionsProvider(k))
      ..invalidate(newsGuardProvider(widget.symbol));
    await ref.read(candlesProvider(k).future);
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final zx = context.zx;
    final p = zx.palette;
    final key = (symbol: widget.symbol, timeframe: _tf);
    final series = ref.watch(liveSeriesProvider(key));
    final live = ref.watch(liveCandleProvider(key)).value;
    final signal = ref.watch(latestSignalProvider(key));
    final instrument = ref.watch(instrumentProvider(widget.symbol));
    final decimals = instrument?.priceDecimals;
    final side = _side ?? (signal.value?.isUp == false ? 'short' : 'long');

    // ATR levels are drawn on the chart while the Levels tab is open
    final levels = _tab == PairTab.levels
        ? ref.watch(levelsProvider((symbol: widget.symbol, timeframe: _tf, side: side))).value
        : null;
    final entry = levels?.entry;
    final stop = levels?.stop;
    final target = levels?.targets.where((t) => t.price != null).firstOrNull?.price;

    return ZxPage(
      title: widget.symbol,
      onRefresh: _refresh,
      children: [
        _LiveHeader(series: series.value, live: live, decimals: decimals, name: instrument?.displayName),
        ZxSegmented<String>(
          segments: [for (final tf in chartTimeframes) (tf, tf)],
          selected: _tf,
          onChanged: (v) => setState(() => _tf = v),
        ),
        GlassCard(
          padding: const EdgeInsets.fromLTRB(ZxSpace.sm, ZxSpace.md, ZxSpace.xs, ZxSpace.xs),
          child: AsyncValueView<CandleSeries>(
            value: series,
            onRetry: () => ref.invalidate(candlesProvider(key)),
            data: (s) => CandleChart(
              candles: s.candles,
              decimals: decimals,
              timeframe: _tf,
              live: live == null ? null : ChartLive.from(live),
              zones: [
                if (entry != null && stop != null) ChartZone(from: entry, to: stop, color: p.bearish),
                if (entry != null && target != null) ChartZone(from: entry, to: target, color: p.bullish),
              ],
              levels: [
                if (entry != null) ChartLevel(price: entry, label: l.entry, color: p.accentAlt),
                if (stop != null) ChartLevel(price: stop, label: l.stop, color: p.bearish),
                for (final (i, t) in (levels?.targets ?? const <LevelTarget>[]).indexed)
                  if (t.price != null) ChartLevel(price: t.price!, label: 'T${i + 1}', color: p.bullish),
              ],
            ),
          ),
        ),
        ZxSegmented<PairTab>(
          segments: [
            (PairTab.signal, l.tabSignal),
            (PairTab.levels, l.tabLevels),
            (PairTab.conditions, l.tabConditions),
            (PairTab.news, l.tabNews),
          ],
          selected: _tab,
          onChanged: (v) => setState(() => _tab = v),
        ),
        AnimatedSwitcher(
          duration: reduceMotion(context) ? Duration.zero : ZxMotion.normal,
          switchInCurve: ZxMotion.emphasized,
          transitionBuilder: (child, a) => FadeTransition(
            opacity: a,
            child: SlideTransition(
              position: Tween(begin: const Offset(0, 0.02), end: Offset.zero).animate(a),
              child: child,
            ),
          ),
          child: KeyedSubtree(
            key: ValueKey(_tab),
            child: switch (_tab) {
              PairTab.signal => AsyncValueView<Signal?>(
                value: signal,
                compact: true,
                onRetry: () => ref.invalidate(latestSignalProvider(key)),
                data: (s) => s == null
                    ? GlassCard(child: Text(l.noSignalYet, style: zx.text.secondary))
                    : SignalCard(signal: s),
              ),
              PairTab.levels => LevelsCard(
                symbol: widget.symbol,
                timeframe: _tf,
                side: side,
                onSide: (s) => setState(() => _side = s),
              ),
              PairTab.conditions => ConditionsCard(symbol: widget.symbol, timeframe: _tf),
              PairTab.news => NewsGuardCard(symbol: widget.symbol),
            },
          ),
        ),
        const Disclaimer(),
      ],
    );
  }
}

/// Price, 24h change and the feed status (live ticks, or updates at each close).
class _LiveHeader extends StatelessWidget {
  const _LiveHeader({required this.series, required this.live, required this.decimals, this.name});

  final CandleSeries? series;
  final LiveCandle? live;
  final int? decimals;
  final String? name;

  @override
  Widget build(BuildContext context) {
    final zx = context.zx;
    final l = context.l10n;
    final p = zx.palette;
    final candles = series?.candles ?? const <Candle>[];
    final last = candles.isEmpty ? null : candles.last;
    final change = last == null ? null : change24h(candles);
    final feed = live;
    final isLive = feed?.live ?? false;
    final closed = feed != null && !feed.marketOpen;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(child: Text(name ?? '', style: zx.text.caption, overflow: TextOverflow.ellipsis)),
            if (feed != null)
              Tooltip(
                message: feed.note ?? '',
                child: Pill(
                  label: closed ? l.marketClosed : (isLive ? l.liveBadge : l.updatesAtClose),
                  color: closed ? p.neutral : (isLive ? p.bullish : p.textSecondary),
                  background: closed ? p.neutralSoft : (isLive ? p.bullishSoft : p.glass),
                  icon: isLive ? null : Icons.schedule_rounded,
                ),
              ),
            if (isLive && !closed) ...[
              const SizedBox(width: ZxSpace.sm),
              StatusOrb(color: p.bullish, size: ZxSize.orb * 0.7),
            ],
          ],
        ),
        const SizedBox(height: ZxSpace.xs),
        Wrap(
          crossAxisAlignment: WrapCrossAlignment.center,
          spacing: ZxSpace.md,
          runSpacing: ZxSpace.xs,
          children: [
            FlashOnChange(
              value: last?.c,
              child: Text(Fmt.price(last?.c, decimals: decimals), style: zx.text.heroPrice),
            ),
            ChangePill(pct: change, suffix: l.change24h),
          ],
        ),
        if (last != null && !isLive)
          Padding(
            padding: const EdgeInsets.only(top: ZxSpace.xs),
            child: Text('${l.lastClose} · ${Fmt.dateTime(last.t, context.localeCode)}', style: zx.text.caption),
          ),
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

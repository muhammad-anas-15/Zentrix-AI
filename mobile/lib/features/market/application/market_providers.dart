import 'dart:async';

import 'package:flutter/widgets.dart' show AppLifecycleListener;
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/market_repository.dart';
import '../domain/models.dart';

typedef SeriesKey = ({String symbol, String timeframe});
typedef LevelsKey = ({String symbol, String timeframe, String side});

/// Markets the dashboard and calculator offer first.
const defaultSymbols = <String>['EUR/USD', 'GBP/USD', 'XAU/USD', 'USD/JPY', 'BTC/USDT'];
const chartTimeframes = <String>['5m', '15m', '1h', '4h', '1d'];
const defaultTimeframe = '15m';

final instrumentsProvider = FutureProvider<List<Instrument>>(
  (ref) => ref.watch(marketRepositoryProvider).instruments(),
);

/// Instrument by symbol (for price decimals), once the list is loaded.
final instrumentProvider = Provider.family<Instrument?, String>((ref, symbol) {
  final list = ref.watch(instrumentsProvider).value;
  if (list == null) return null;
  for (final i in list) {
    if (i.symbol == symbol) return i;
  }
  return null;
});

final candlesProvider = FutureProvider.autoDispose.family<CandleSeries, SeriesKey>(
  (ref, k) => ref.watch(marketRepositoryProvider).candles(k.symbol, k.timeframe),
);

/// Polls the live candle while a chart is on screen, as often as the server suggests (2 s on exchange feeds,
/// around each candle close elsewhere). Errors keep the last value and retry; polling pauses in the background.
final liveCandleProvider = StreamProvider.autoDispose.family<LiveCandle, SeriesKey>((ref, k) {
  final repo = ref.watch(marketRepositoryProvider);
  final controller = StreamController<LiveCandle>();
  Timer? timer;
  var active = true;
  var hidden = false;
  var delivered = false;

  Future<void> poll() async {
    timer?.cancel();
    if (!active || hidden) return;
    var wait = const Duration(seconds: 10);
    try {
      final live = await repo.liveCandle(k.symbol, k.timeframe);
      if (!active) return;
      controller.add(live);
      delivered = true;
      wait = Duration(seconds: live.pollS.clamp(1, 60));
    } on Object catch (e, st) {
      if (!active) return;
      if (!delivered) controller.addError(e, st);
    }
    if (active && !hidden) timer = Timer(wait, poll);
  }

  final lifecycle = AppLifecycleListener(
    onHide: () {
      hidden = true;
      timer?.cancel();
    },
    onShow: () {
      hidden = false;
      poll();
    },
  );
  poll();
  ref.onDispose(() {
    active = false;
    timer?.cancel();
    lifecycle.dispose();
    controller.close();
  });
  return controller.stream;
});

/// Stored candles with the live candle merged in: the chart's series.
final liveSeriesProvider = Provider.autoDispose.family<AsyncValue<CandleSeries>, SeriesKey>((ref, k) {
  final base = ref.watch(candlesProvider(k));
  final live = ref.watch(liveCandleProvider(k)).value;
  return base.whenData((s) => live == null ? s : s.copyWith(candles: mergeLive(s.candles, live)));
});

/// [base] with the live response applied: the just-closed candle gets its final values, the forming candle
/// replaces or extends the last one. On closed-candle feeds a newly stored close is appended.
List<Candle> mergeLive(List<Candle> base, LiveCandle live) {
  final out = [...base];
  void put(Candle c) {
    if (out.isEmpty || c.t.isAfter(out.last.t)) {
      out.add(c);
      return;
    }
    for (var i = out.length - 1; i >= 0 && i >= out.length - 3; i--) {
      if (out[i].t == c.t) {
        out[i] = c;
        return;
      }
      if (out[i].t.isBefore(c.t)) {
        out.insert(i + 1, c);
        return;
      }
    }
  }

  final closed = live.closed;
  final candle = live.candle;
  if (closed != null) put(closed);
  if (candle != null) put(candle);
  return out;
}

final latestSignalProvider = FutureProvider.autoDispose.family<Signal?, SeriesKey>(
  (ref, k) => ref.watch(marketRepositoryProvider).latestSignal(k.symbol, k.timeframe),
);

final conditionsProvider = FutureProvider.autoDispose.family<Conditions, SeriesKey>(
  (ref, k) => ref.watch(marketRepositoryProvider).conditions(k.symbol, k.timeframe),
);

final newsGuardProvider = FutureProvider.autoDispose.family<NewsGuard, String>(
  (ref, symbol) => ref.watch(marketRepositoryProvider).newsGuard(symbol),
);

final levelsProvider = FutureProvider.autoDispose.family<Levels, LevelsKey>(
  (ref, k) => ref.watch(marketRepositoryProvider).levels(k.symbol, k.timeframe, k.side),
);

/// Refetch the Radar every minute while it is on screen (the last data stays visible meanwhile).
final radarClockProvider = StreamProvider.autoDispose<int>(
  (ref) => Stream<int>.periodic(const Duration(minutes: 1), (i) => i + 1),
);

final radarProvider = FutureProvider.autoDispose<Radar>((ref) {
  ref.watch(radarClockProvider);
  return ref.watch(marketRepositoryProvider).radar(timeframe: defaultTimeframe);
});

final scenarioProvider = FutureProvider.autoDispose.family<Scenario?, SeriesKey>(
  (ref, k) => ref.watch(marketRepositoryProvider).scenario(k.symbol, k.timeframe),
);

/// The market the dashboard focuses on.
class FocusSymbol extends Notifier<String> {
  @override
  String build() => defaultSymbols.first;

  void select(String symbol) => state = symbol;
}

final focusSymbolProvider = NotifierProvider<FocusSymbol, String>(FocusSymbol.new);

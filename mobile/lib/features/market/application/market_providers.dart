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

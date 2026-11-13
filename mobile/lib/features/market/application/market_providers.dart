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

/// The market the dashboard focuses on.
class FocusSymbol extends Notifier<String> {
  @override
  String build() => defaultSymbols.first;

  void select(String symbol) => state = symbol;
}

final focusSymbolProvider = NotifierProvider<FocusSymbol, String>(FocusSymbol.new);

/// Last close and change over ~24h from stored 15m candles (guests have no watchlist quotes).
typedef MiniQuote = ({String symbol, double? price, double? change24hPct, List<double> spark});

final miniQuoteProvider = FutureProvider.autoDispose.family<MiniQuote, String>((ref, symbol) async {
  final series = await ref.watch(marketRepositoryProvider).candles(symbol, '15m', limit: 97);
  final closes = [for (final c in series.candles) c.c];
  if (closes.isEmpty) return (symbol: symbol, price: null, change24hPct: null, spark: const <double>[]);
  final first = closes.first;
  return (
    symbol: symbol,
    price: closes.last,
    change24hPct: closes.length > 1 && first != 0 ? (closes.last / first - 1) * 100 : null,
    spark: closes,
  );
});

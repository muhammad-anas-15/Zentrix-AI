import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/providers.dart';
import '../domain/models.dart';

Map<String, dynamic> _map(Object? json) => json! as Map<String, dynamic>;

/// Public market endpoints: instruments, candles, signals, conditions, news guard, ATR levels.
class MarketRepository {
  MarketRepository(this._api);

  final ApiClient _api;

  Future<List<Instrument>> instruments() =>
      _api.get('/v1/instruments', (j) => InstrumentPage.fromJson(_map(j)).items, query: {'limit': 200});

  Future<CandleSeries> candles(String symbol, String timeframe, {int limit = 300}) => _api.get(
    '/v1/candles',
    (j) => CandleSeries.fromJson(_map(j)),
    query: {'symbol': symbol, 'timeframe': timeframe, 'limit': limit},
  );

  /// The forming candle for a live chart (or the latest closed one where the feed has no ticks).
  Future<LiveCandle> liveCandle(String symbol, String timeframe) => _api.get(
    '/v1/candles/live',
    (j) => LiveCandle.fromJson(_map(j)),
    query: {'symbol': symbol, 'timeframe': timeframe},
  );

  /// Latest signal, or null when there is none yet (404 no_signal).
  Future<Signal?> latestSignal(String symbol, String timeframe, {int horizon = 1}) async {
    try {
      return await _api.get(
        '/v1/signals/latest',
        (j) => Signal.fromJson(_map(j)),
        query: {'symbol': symbol, 'timeframe': timeframe, 'horizon': horizon},
      );
    } on ApiException catch (e) {
      if (e.code == 'no_signal') return null;
      rethrow;
    }
  }

  Future<SignalPage> signals({String? symbol, String? status, int limit = 50}) => _api.get(
    '/v1/signals',
    (j) => SignalPage.fromJson(_map(j)),
    query: {'symbol': symbol, 'status': status, 'limit': limit},
  );

  Future<Conditions> conditions(String symbol, String timeframe) => _api.get(
    '/v1/conditions',
    (j) => Conditions.fromJson(_map(j)),
    query: {'symbol': symbol, 'timeframe': timeframe},
  );

  Future<NewsGuard> newsGuard(String symbol) =>
      _api.get('/v1/news/guard', (j) => NewsGuard.fromJson(_map(j)), query: {'symbol': symbol});

  /// Every ingested market ranked by conditions, then activity.
  Future<Radar> radar({String timeframe = '15m'}) =>
      _api.get('/v1/radar', (j) => Radar.fromJson(_map(j)), query: {'timeframe': timeframe});

  /// Expected range for the next [steps] candles, with the measured coverage of such bands; null without enough
  /// stored history (404 no_data).
  Future<Scenario?> scenario(String symbol, String timeframe, {int steps = 5}) async {
    try {
      return await _api.get(
        '/v1/scenario',
        (j) => Scenario.fromJson(_map(j)),
        query: {'symbol': symbol, 'timeframe': timeframe, 'steps': steps},
      );
    } on ApiException catch (e) {
      if (e.code == 'no_data') return null;
      rethrow;
    }
  }

  /// Technical Pattern Projection for the next [steps] candles; null without enough stored history (404 no_data).
  Future<PatternOutlook?> patterns(String symbol, String timeframe, {int steps = 5}) async {
    try {
      return await _api.get(
        '/v1/patterns',
        (j) => PatternOutlook.fromJson(_map(j)),
        query: {'symbol': symbol, 'timeframe': timeframe, 'steps': steps},
      );
    } on ApiException catch (e) {
      if (e.code == 'no_data') return null;
      rethrow;
    }
  }

  Future<Levels> levels(String symbol, String timeframe, String side) => _api.get(
    '/v1/levels',
    (j) => Levels.fromJson(_map(j)),
    query: {'symbol': symbol, 'timeframe': timeframe, 'side': side},
  );
}

final marketRepositoryProvider = Provider<MarketRepository>((ref) => MarketRepository(ref.watch(apiClientProvider)));

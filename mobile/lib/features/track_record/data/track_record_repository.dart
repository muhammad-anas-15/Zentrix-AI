import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../../../core/providers.dart';
import '../../market/data/market_repository.dart';
import '../../market/domain/models.dart';
import '../domain/models.dart';

Map<String, dynamic> _map(Object? json) => json! as Map<String, dynamic>;

class TrackRecordRepository {
  TrackRecordRepository(this._api);

  final ApiClient _api;

  Future<TrackRecord> trackRecord() => _api.get('/v1/track-record', (j) => TrackRecord.fromJson(_map(j)));
}

final trackRecordRepositoryProvider = Provider<TrackRecordRepository>(
  (ref) => TrackRecordRepository(ref.watch(apiClientProvider)),
);

final trackRecordProvider = FutureProvider.autoDispose<TrackRecord>(
  (ref) => ref.watch(trackRecordRepositoryProvider).trackRecord(),
);

final recentResolvedSignalsProvider = FutureProvider.autoDispose<SignalPage>(
  (ref) => ref.watch(marketRepositoryProvider).signals(status: 'resolved', limit: 30),
);

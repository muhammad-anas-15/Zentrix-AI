import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../../../core/providers.dart';
import '../domain/models.dart';

Map<String, dynamic> _map(Object? json) => json! as Map<String, dynamic>;

/// Market Pulse: headlines (`/v1/news/feed`) and the economic calendar (`/v1/news/events`).
class PulseRepository {
  PulseRepository(this._api);

  final ApiClient _api;

  Future<NewsFeed> feed({String? asset, String? impact, String? kind, int limit = 40}) => _api.get(
    '/v1/news/feed',
    (j) => NewsFeed.fromJson(_map(j)),
    query: {'asset': asset, 'impact': impact, 'kind': kind, 'limit': limit},
  );

  Future<CalendarPage> calendar({String impact = 'medium', required DateTime start, required DateTime end}) =>
      _api.get(
        '/v1/news/events',
        (j) => CalendarPage.fromJson(_map(j)),
        query: {'impact': impact, 'start': start.toUtc().toIso8601String(), 'end': end.toUtc().toIso8601String()},
      );
}

final pulseRepositoryProvider = Provider<PulseRepository>((ref) => PulseRepository(ref.watch(apiClientProvider)));

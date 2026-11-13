import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../../../core/providers.dart';
import '../../auth/application/session.dart';
import '../domain/models.dart';

Map<String, dynamic> _map(Object? json) => json! as Map<String, dynamic>;
List<Object?> _list(Object? json) => json! as List<Object?>;

/// Alerts, the alert inbox and watchlists (signed-in users).
class AlertsRepository {
  AlertsRepository(this._api);

  final ApiClient _api;

  Future<List<Alert>> alerts() => _api.get('/v1/alerts', (j) => [for (final a in _list(j)) Alert.fromJson(_map(a))]);

  Future<Alert> create(Map<String, Object?> body) =>
      _api.post('/v1/alerts', (j) => Alert.fromJson(_map(j)), body: body);

  Future<Alert> setActive(int id, {required bool active}) =>
      _api.patch('/v1/alerts/$id', (j) => Alert.fromJson(_map(j)), body: {'active': active});

  Future<void> delete(int id) => _api.delete('/v1/alerts/$id');

  Future<AlertInbox> inbox() =>
      _api.get('/v1/alerts/events', (j) => AlertInbox.fromJson(_map(j)), query: {'limit': 100});

  Future<void> markAllRead() => _api.post('/v1/alerts/events/read', (_) {}, body: {'all': true});

  Future<List<Watchlist>> watchlists() =>
      _api.get('/v1/watchlists', (j) => [for (final w in _list(j)) Watchlist.fromJson(_map(w))]);

  Future<Watchlist> createWatchlist(String name, List<String> symbols) =>
      _api.post('/v1/watchlists', (j) => Watchlist.fromJson(_map(j)), body: {'name': name, 'symbols': symbols});

  Future<Quotes> quotes(int watchlistId) =>
      _api.get('/v1/watchlists/$watchlistId/quotes', (j) => Quotes.fromJson(_map(j)));
}

final alertsRepositoryProvider = Provider<AlertsRepository>((ref) => AlertsRepository(ref.watch(apiClientProvider)));

/// Providers return empty results for guests, so screens can render without an account.
final alertsProvider = FutureProvider.autoDispose<List<Alert>>((ref) async {
  if (ref.watch(currentUserProvider) == null) return const [];
  return ref.watch(alertsRepositoryProvider).alerts();
});

final inboxProvider = FutureProvider.autoDispose<AlertInbox>((ref) async {
  if (ref.watch(currentUserProvider) == null) return const AlertInbox(items: [], unread: 0);
  return ref.watch(alertsRepositoryProvider).inbox();
});

final watchlistsProvider = FutureProvider.autoDispose<List<Watchlist>>((ref) async {
  if (ref.watch(currentUserProvider) == null) return const [];
  return ref.watch(alertsRepositoryProvider).watchlists();
});

final quotesProvider = FutureProvider.autoDispose.family<Quotes, int>(
  (ref, id) => ref.watch(alertsRepositoryProvider).quotes(id),
);

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../../../core/providers.dart';
import '../../auth/application/session.dart';
import '../domain/models.dart';

Map<String, dynamic> _map(Object? json) => json! as Map<String, dynamic>;

/// Trade journal (signed-in users). P&L and R are computed by the server.
class JournalRepository {
  JournalRepository(this._api);

  final ApiClient _api;

  Future<JournalPage> list({int limit = 100}) =>
      _api.get('/v1/journal', (j) => JournalPage.fromJson(_map(j)), query: {'limit': limit});

  Future<JournalEntry> create(NewTrade trade) =>
      _api.post('/v1/journal', (j) => JournalEntry.fromJson(_map(j)), body: trade.toJson());

  Future<JournalEntry> close(int id, {required double exitPrice, required DateTime exitAt}) => _api.patch(
    '/v1/journal/$id',
    (j) => JournalEntry.fromJson(_map(j)),
    body: {'exit_price': exitPrice, 'exit_at': exitAt.toUtc().toIso8601String()},
  );

  Future<void> delete(int id) => _api.delete('/v1/journal/$id');

  Future<JournalStats> stats() => _api.get('/v1/journal/stats', (j) => JournalStats.fromJson(_map(j)));
}

final journalRepositoryProvider = Provider<JournalRepository>((ref) => JournalRepository(ref.watch(apiClientProvider)));

final journalProvider = FutureProvider.autoDispose<JournalPage>((ref) async {
  if (ref.watch(currentUserProvider) == null) return const JournalPage(items: []);
  return ref.watch(journalRepositoryProvider).list();
});

final journalStatsProvider = FutureProvider.autoDispose<JournalStats>(
  (ref) => ref.watch(journalRepositoryProvider).stats(),
);

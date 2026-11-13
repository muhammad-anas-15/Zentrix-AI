import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../../../core/providers.dart';
import '../domain/models.dart';

Map<String, dynamic> _map(Object? json) => json! as Map<String, dynamic>;

class RiskRepository {
  RiskRepository(this._api);

  final ApiClient _api;

  /// Public; personalised (risk profile, daily loss budget) when signed in.
  Future<PositionSize> positionSize(PositionSizeRequest request) =>
      _api.post('/v1/risk/position-size', (j) => PositionSize.fromJson(_map(j)), body: request.toJson());

  Future<RiskStatus> status() => _api.get('/v1/me/risk-status', (j) => RiskStatus.fromJson(_map(j)));
}

final riskRepositoryProvider = Provider<RiskRepository>((ref) => RiskRepository(ref.watch(apiClientProvider)));

import 'package:freezed_annotation/freezed_annotation.dart';

import '../../../core/models/premium.dart';

part 'models.freezed.dart';
part 'models.g.dart';

/// Input of `POST /v1/risk/position-size`. Empty optional fields fall back to the risk profile on the server.
@freezed
abstract class PositionSizeRequest with _$PositionSizeRequest {
  const factory PositionSizeRequest({
    required String symbol,
    required double entry,
    required double stop,
    double? takeProfit,
    String? accountCurrency,
    double? balance,
    double? riskPct,
    double? leverage,
    @Default('15m') String timeframe,
  }) = _PositionSizeRequest;

  factory PositionSizeRequest.fromJson(Map<String, dynamic> json) => _$PositionSizeRequestFromJson(json);
}

@freezed
abstract class PositionSize with _$PositionSize {
  const factory PositionSize({
    required String symbol,
    required String side,
    required String accountCurrency,
    required double units,
    double? lots,
    double? contractSize,
    required double riskAmount,
    double? riskPct,
    required double stopDistance,
    double? stopPips,
    double? stopAtr,
    double? pipSize,
    double? pipValuePerLot,
    required double pointSize,
    double? rewardAmount,
    double? riskReward,
    required double notional,
    double? margin,
    required double conversionRate,
    @Default(<String>[]) List<String> conversionNotes,
    double? dailyLossLeft,
    @Default(<String>[]) List<String> warnings,
    @Default(<String>[]) List<String> premiumLocked,
  }) = _PositionSize;

  factory PositionSize.fromJson(Map<String, dynamic> json) => _$PositionSizeFromJson(json);
}

@freezed
abstract class RiskWarning with _$RiskWarning {
  const factory RiskWarning({required String code, required String message}) = _RiskWarning;

  factory RiskWarning.fromJson(Map<String, dynamic> json) => _$RiskWarningFromJson(json);
}

/// `GET /v1/me/risk-status` (Premium: risk_guard).
@freezed
abstract class RiskStatus with _$RiskStatus {
  const factory RiskStatus({
    required String level,
    required List<RiskWarning> warnings,
    required String accountCurrency,
    required double realizedPnlToday,
    double? dailyLossLimit,
    required double dailyLossUsed,
    double? dailyLossLeft,
    required int tradesToday,
    required int maxTradesPerDay,
    required int openPositions,
    required double openRisk,
    required int consecutiveLosses,
    PremiumBadge? premium,
  }) = _RiskStatus;

  factory RiskStatus.fromJson(Map<String, dynamic> json) => _$RiskStatusFromJson(json);
}

import 'package:freezed_annotation/freezed_annotation.dart';

import '../../../core/models/premium.dart';

part 'models.freezed.dart';
part 'models.g.dart';

@freezed
abstract class Listing with _$Listing {
  const factory Listing({
    required String venue,
    required String venueSymbol,
    required String status,
    required bool isPrimary,
    String? note,
  }) = _Listing;

  factory Listing.fromJson(Map<String, dynamic> json) => _$ListingFromJson(json);
}

@freezed
abstract class Instrument with _$Instrument {
  const Instrument._();

  const factory Instrument({
    required String symbol,
    required String displayName,
    required String assetClass,
    required String instrumentType,
    required String base,
    required String quote,
    double? contractSize,
    required int priceDecimals,
    required String session,
    required bool active,
    @Default(<Listing>[]) List<Listing> listings,
  }) = _Instrument;

  factory Instrument.fromJson(Map<String, dynamic> json) => _$InstrumentFromJson(json);

  /// Has a primary feed that is ingesting data.
  bool get hasLiveFeed => listings.any((l) => l.isPrimary && l.status == 'active');
}

@freezed
abstract class InstrumentPage with _$InstrumentPage {
  const factory InstrumentPage({required List<Instrument> items, required int total}) = _InstrumentPage;

  factory InstrumentPage.fromJson(Map<String, dynamic> json) => _$InstrumentPageFromJson(json);
}

/// One closed candle (`t` = open time, UTC).
@freezed
abstract class Candle with _$Candle {
  const factory Candle({
    required DateTime t,
    required double o,
    required double h,
    required double l,
    required double c,
    double? v,
  }) = _Candle;

  factory Candle.fromJson(Map<String, dynamic> json) => _$CandleFromJson(json);
}

@freezed
abstract class CandleSeries with _$CandleSeries {
  const factory CandleSeries({
    required String symbol,
    required String venue,
    required String timeframe,
    required List<Candle> candles,
  }) = _CandleSeries;

  factory CandleSeries.fromJson(Map<String, dynamic> json) => _$CandleSeriesFromJson(json);
}

@freezed
abstract class SignalModel with _$SignalModel {
  const factory SignalModel({required String key, required DateTime trainedAt, required bool hasDemonstratedEdge}) =
      _SignalModel;

  factory SignalModel.fromJson(Map<String, dynamic> json) => _$SignalModelFromJson(json);
}

@freezed
abstract class SignalOutcome with _$SignalOutcome {
  const factory SignalOutcome({
    required String outcome,
    DateTime? entryTime,
    double? entryPrice,
    DateTime? exitTime,
    double? exitPrice,
    double? movePct,
    required DateTime resolvedAt,
    String? note,
  }) = _SignalOutcome;

  factory SignalOutcome.fromJson(Map<String, dynamic> json) => _$SignalOutcomeFromJson(json);
}

/// A live signal. `strength` is shown exactly as the server sends it.
@freezed
abstract class Signal with _$Signal {
  const Signal._();

  const factory Signal({
    required int id,
    required String symbol,
    required String venue,
    required String timeframe,
    required int horizon,
    required DateTime candleTime,
    required DateTime decisionAt,
    required DateTime createdAt,
    required String direction,
    required double confidence,
    required double pUp,
    required String strength,
    required SignalModel model,
    Map<String, dynamic>? backtestTier,
    SignalOutcome? outcome,
    PremiumBadge? premium,
  }) = _Signal;

  factory Signal.fromJson(Map<String, dynamic> json) => _$SignalFromJson(json);

  static const noEdgeStrength = 'Very Weak - Wait';

  bool get isUp => direction == 'up';

  /// Direction is only evidence when the model earned a tier out of sample.
  bool get isActionable => model.hasDemonstratedEdge && strength != noEdgeStrength;
}

@freezed
abstract class SignalPage with _$SignalPage {
  const factory SignalPage({
    required List<Signal> items,
    int? nextBeforeId,
    @Default(<String>[]) List<String> premiumLocked,
  }) = _SignalPage;

  factory SignalPage.fromJson(Map<String, dynamic> json) => _$SignalPageFromJson(json);
}

@freezed
abstract class ConditionFactor with _$ConditionFactor {
  const factory ConditionFactor({required String name, required String status, Object? value, required String detail}) =
      _ConditionFactor;

  factory ConditionFactor.fromJson(Map<String, dynamic> json) => _$ConditionFactorFromJson(json);
}

/// `GET /v1/conditions`: the market-condition light.
@freezed
abstract class Conditions with _$Conditions {
  const factory Conditions({
    required String symbol,
    required String venue,
    required String timeframe,
    required String light,
    required List<ConditionFactor> factors,
    @Default(<String, dynamic>{}) Map<String, dynamic> trend,
    @Default(<String, dynamic>{}) Map<String, dynamic> volatility,
    @Default(<String>[]) List<String> sessions,
    DateTime? lastCandleClose,
    required String method,
  }) = _Conditions;

  factory Conditions.fromJson(Map<String, dynamic> json) => _$ConditionsFromJson(json);
}

@freezed
abstract class NewsEvent with _$NewsEvent {
  const factory NewsEvent({
    required String title,
    required String currency,
    required String impact,
    required DateTime eventAt,
    required int inS,
    String? forecast,
    String? previous,
    String? actual,
  }) = _NewsEvent;

  factory NewsEvent.fromJson(Map<String, dynamic> json) => _$NewsEventFromJson(json);
}

/// `GET /v1/news/guard`.
@freezed
abstract class NewsGuard with _$NewsGuard {
  const factory NewsGuard({
    required String symbol,
    required String state,
    @Default(<String>[]) List<String> currencies,
    @Default(<String>[]) List<String> reasons,
    @Default(<NewsEvent>[]) List<NewsEvent> activeEvents,
    NewsEvent? nextEvent,
    int? countdownS,
    DateTime? blackoutUntil,
    DateTime? calendarUpdatedAt,
  }) = _NewsGuard;

  factory NewsGuard.fromJson(Map<String, dynamic> json) => _$NewsGuardFromJson(json);
}

@freezed
abstract class BaseRate with _$BaseRate {
  const factory BaseRate({
    required double r,
    double? hitRate,
    List<double?>? ci95,
    required double breakEvenHitRate,
    required int entries,
    required int targetFirst,
    required int stopFirst,
    required int neitherWithinMaxBars,
    required int maxBars,
  }) = _BaseRate;

  factory BaseRate.fromJson(Map<String, dynamic> json) => _$BaseRateFromJson(json);
}

@freezed
abstract class LevelTarget with _$LevelTarget {
  const factory LevelTarget({required double r, double? price, required BaseRate baseRate}) = _LevelTarget;

  factory LevelTarget.fromJson(Map<String, dynamic> json) => _$LevelTargetFromJson(json);
}

/// `GET /v1/levels`: ATR stop and targets (Premium).
@freezed
abstract class Levels with _$Levels {
  const factory Levels({
    required String symbol,
    required String timeframe,
    required String side,
    double? entry,
    double? atr,
    required double slAtr,
    double? stop,
    required List<LevelTarget> targets,
    double? support,
    double? resistance,
    required DateTime asOf,
    int? signalId,
    @Default(<String>[]) List<String> notes,
    required String method,
    PremiumBadge? premium,
  }) = _Levels;

  factory Levels.fromJson(Map<String, dynamic> json) => _$LevelsFromJson(json);
}

/// One market on the Radar (`GET /v1/radar`): conditions now, recent movement. No direction call.
@freezed
abstract class RadarItem with _$RadarItem {
  const RadarItem._();

  const factory RadarItem({
    required int rank,
    required String symbol,
    required String displayName,
    required String assetClass,
    String? venue,
    required int priceDecimals,
    required String light,
    @Default(<String>[]) List<String> reasons,
    String? trendRegime,
    String? trendDirection,
    double? adx,
    String? volatilityRegime,
    double? volatilityPercentile,
    required String newsState,
    NewsEvent? nextEvent,
    int? nextEventInS,
    @Default(<String>[]) List<String> sessions,
    double? lastPrice,
    DateTime? lastCandleClose,
    @JsonKey(name: 'change_24h_pct') double? change24hPct,
    @Default(<double>[]) List<double> spark,
  }) = _RadarItem;

  factory RadarItem.fromJson(Map<String, dynamic> json) => _$RadarItemFromJson(json);

  bool get hasData => lastPrice != null;
}

@freezed
abstract class Radar with _$Radar {
  const factory Radar({
    required String timeframe,
    required DateTime asOf,
    required List<RadarItem> items,
    required String ranking,
  }) = _Radar;

  factory Radar.fromJson(Map<String, dynamic> json) => _$RadarFromJson(json);
}

/// One step of the expected range (`GET /v1/scenario`): an 80% price band and how often such bands held.
@freezed
abstract class ScenarioStep with _$ScenarioStep {
  const factory ScenarioStep({
    required int k,
    required DateTime at,
    double? low,
    double? median,
    double? high,
    required double nominalCoverage,
    double? coverage,
    List<double?>? coverageCi95,
    required int coverageTested,
  }) = _ScenarioStep;

  factory ScenarioStep.fromJson(Map<String, dynamic> json) => _$ScenarioStepFromJson(json);
}

@freezed
abstract class Scenario with _$Scenario {
  const factory Scenario({
    required String symbol,
    required String timeframe,
    required double lastClose,
    required DateTime asOf,
    required List<ScenarioStep> steps,
    required String method,
    PremiumBadge? premium,
  }) = _Scenario;

  factory Scenario.fromJson(Map<String, dynamic> json) => _$ScenarioFromJson(json);
}

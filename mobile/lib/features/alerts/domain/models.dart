import 'package:freezed_annotation/freezed_annotation.dart';

import '../../../core/models/premium.dart';

part 'models.freezed.dart';
part 'models.g.dart';

@freezed
abstract class Alert with _$Alert {
  const factory Alert({
    required int id,
    required String kind,
    String? symbol,
    int? watchlistId,
    String? timeframe,
    @Default(<String, dynamic>{}) Map<String, dynamic> params,
    required bool active,
    required bool recurring,
    required int cooldownS,
    String? note,
    DateTime? lastTriggeredAt,
    required int triggerCount,
    required DateTime createdAt,
    PremiumBadge? premium,
  }) = _Alert;

  factory Alert.fromJson(Map<String, dynamic> json) => _$AlertFromJson(json);
}

@freezed
abstract class AlertEvent with _$AlertEvent {
  const AlertEvent._();

  const factory AlertEvent({
    required int id,
    int? alertId,
    required String kind,
    required String title,
    required String body,
    @Default(<String, dynamic>{}) Map<String, dynamic> data,
    required DateTime triggeredAt,
    required String delivery,
    DateTime? readAt,
  }) = _AlertEvent;

  factory AlertEvent.fromJson(Map<String, dynamic> json) => _$AlertEventFromJson(json);

  bool get unread => readAt == null;
}

@freezed
abstract class AlertInbox with _$AlertInbox {
  const factory AlertInbox({required List<AlertEvent> items, int? nextBeforeId, required int unread}) = _AlertInbox;

  factory AlertInbox.fromJson(Map<String, dynamic> json) => _$AlertInboxFromJson(json);
}

@freezed
abstract class WatchlistItem with _$WatchlistItem {
  const factory WatchlistItem({
    required String symbol,
    required String displayName,
    required String assetClass,
    required int sortOrder,
  }) = _WatchlistItem;

  factory WatchlistItem.fromJson(Map<String, dynamic> json) => _$WatchlistItemFromJson(json);
}

@freezed
abstract class Watchlist with _$Watchlist {
  const factory Watchlist({
    required int id,
    required String name,
    required int sortOrder,
    required List<WatchlistItem> items,
  }) = _Watchlist;

  factory Watchlist.fromJson(Map<String, dynamic> json) => _$WatchlistFromJson(json);
}

@freezed
abstract class QuoteSignal with _$QuoteSignal {
  const factory QuoteSignal({
    required int id,
    required String timeframe,
    required int horizon,
    required String direction,
    required String strength,
    required double confidence,
    required bool hasDemonstratedEdge,
    PremiumBadge? premium,
  }) = _QuoteSignal;

  factory QuoteSignal.fromJson(Map<String, dynamic> json) => _$QuoteSignalFromJson(json);
}

/// Last closed price, 24h change, news state and latest signal of one instrument.
@freezed
abstract class Quote with _$Quote {
  const factory Quote({
    required String symbol,
    required String displayName,
    double? price,
    DateTime? asOf,
    @JsonKey(name: 'change_24h_pct') double? change24hPct,
    @Default('unknown') String newsState,
    String? nextEvent,
    int? nextEventInS,
    QuoteSignal? latestSignal,
  }) = _Quote;

  factory Quote.fromJson(Map<String, dynamic> json) => _$QuoteFromJson(json);
}

@freezed
abstract class Quotes with _$Quotes {
  const factory Quotes({
    required int watchlistId,
    required List<Quote> items,
    @Default(<String>[]) List<String> premiumLocked,
  }) = _Quotes;

  factory Quotes.fromJson(Map<String, dynamic> json) => _$QuotesFromJson(json);
}

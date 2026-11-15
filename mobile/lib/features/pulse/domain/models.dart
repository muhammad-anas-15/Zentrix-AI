import 'package:freezed_annotation/freezed_annotation.dart';

import '../../market/domain/models.dart';

part 'models.freezed.dart';
part 'models.g.dart';

/// One headline of the Market Pulse (`GET /v1/news/feed`). Title and link only: the article opens at its publisher.
@freezed
abstract class NewsItem with _$NewsItem {
  const factory NewsItem({
    required int id,
    required String source,
    required String sourceName,
    required String kind,
    required String title,
    required String url,
    required DateTime publishedAt,
    required int ageS,
    required String impact,
    required String impactReason,
    @Default(<String>[]) List<String> assets,
  }) = _NewsItem;

  factory NewsItem.fromJson(Map<String, dynamic> json) => _$NewsItemFromJson(json);
}

@freezed
abstract class NewsSource with _$NewsSource {
  const factory NewsSource({
    required String code,
    required String name,
    required String kind,
    required bool ok,
    DateTime? lastOkAt,
    String? lastError,
  }) = _NewsSource;

  factory NewsSource.fromJson(Map<String, dynamic> json) => _$NewsSourceFromJson(json);
}

@freezed
abstract class NewsFeed with _$NewsFeed {
  const factory NewsFeed({
    required List<NewsItem> items,
    int? nextBeforeId,
    @Default(<NewsSource>[]) List<NewsSource> sources,
    DateTime? updatedAt,
    required String method,
    String? coverage,
  }) = _NewsFeed;

  factory NewsFeed.fromJson(Map<String, dynamic> json) => _$NewsFeedFromJson(json);
}

/// `GET /v1/news/events`: scheduled economic events.
@freezed
abstract class CalendarPage with _$CalendarPage {
  const factory CalendarPage({required List<NewsEvent> items, DateTime? calendarUpdatedAt}) = _CalendarPage;

  factory CalendarPage.fromJson(Map<String, dynamic> json) => _$CalendarPageFromJson(json);
}

/// What the Pulse list shows.
enum PulseFilter { all, high, centralBanks, crypto, fx }

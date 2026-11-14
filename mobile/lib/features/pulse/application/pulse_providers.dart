import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/pulse_repository.dart';
import '../domain/models.dart';

/// The Pulse refreshes every minute while it is on screen (the server polls its feeds every 2 minutes).
final pulseClockProvider = StreamProvider.autoDispose<int>(
  (ref) => Stream<int>.periodic(const Duration(minutes: 1), (i) => i + 1),
);

class PulseFilterNotifier extends Notifier<PulseFilter> {
  @override
  PulseFilter build() => PulseFilter.all;

  void select(PulseFilter f) => state = f;
}

final pulseFilterProvider = NotifierProvider<PulseFilterNotifier, PulseFilter>(PulseFilterNotifier.new);

/// An asset badge the user tapped (USD, BTC, ...): narrows the list further. null = any.
class PulseAssetNotifier extends Notifier<String?> {
  @override
  String? build() => null;

  void select(String? asset) => state = asset == state ? null : asset;
}

final pulseAssetProvider = NotifierProvider<PulseAssetNotifier, String?>(PulseAssetNotifier.new);

class PulseLimitNotifier extends Notifier<int> {
  static const page = 40;
  static const max = 100;

  @override
  int build() {
    ref
      ..watch(pulseFilterProvider)
      ..watch(pulseAssetProvider);
    return page;
  }

  void more() => state = (state + page).clamp(page, max);
}

final pulseLimitProvider = NotifierProvider<PulseLimitNotifier, int>(PulseLimitNotifier.new);

/// Query of a filter: (impact, kind, asset).
({String? impact, String? kind, String? asset}) pulseQuery(PulseFilter f, String? asset) => switch (f) {
  PulseFilter.all => (impact: null, kind: null, asset: asset),
  PulseFilter.high => (impact: 'high', kind: null, asset: asset),
  PulseFilter.centralBanks => (impact: null, kind: 'central_bank', asset: asset),
  PulseFilter.crypto => (impact: null, kind: null, asset: asset ?? 'CRYPTO'),
  PulseFilter.fx => (impact: null, kind: null, asset: asset ?? 'USD,EUR,GBP,JPY,CHF,AUD,NZD,CAD,CNY,XAU,XAG,OIL'),
};

final pulseFeedProvider = FutureProvider.autoDispose<NewsFeed>((ref) {
  ref.watch(pulseClockProvider);
  final q = pulseQuery(ref.watch(pulseFilterProvider), ref.watch(pulseAssetProvider));
  return ref
      .watch(pulseRepositoryProvider)
      .feed(asset: q.asset, impact: q.impact, kind: q.kind, limit: ref.watch(pulseLimitProvider));
});

/// The most important recent headlines, for the Home teaser.
final pulseHeadlinesProvider = FutureProvider.autoDispose<NewsFeed>((ref) {
  ref.watch(pulseClockProvider);
  return ref.watch(pulseRepositoryProvider).feed(impact: 'medium', limit: 3);
});

/// Calendar events from 2 hours ago to 2 days ahead (medium and high impact).
final pulseCalendarProvider = FutureProvider.autoDispose<CalendarPage>((ref) {
  ref.watch(pulseClockProvider);
  final now = DateTime.now();
  return ref
      .watch(pulseRepositoryProvider)
      .calendar(start: now.subtract(const Duration(hours: 2)), end: now.add(const Duration(days: 2)));
});

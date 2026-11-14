import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:zentrix/core/l10n.dart';
import 'package:zentrix/core/theme/theme.dart';
import 'package:zentrix/core/theme/tokens.dart';
import 'package:zentrix/core/widgets/charts.dart';
import 'package:zentrix/core/widgets/controls.dart';
import 'package:zentrix/features/auth/application/session.dart';
import 'package:zentrix/features/dashboard/presentation/dashboard_screen.dart';
import 'package:zentrix/features/journal/domain/models.dart';
import 'package:zentrix/features/journal/presentation/journal_screen.dart';
import 'package:zentrix/features/market/application/market_providers.dart';
import 'package:zentrix/features/market/data/market_repository.dart';
import 'package:zentrix/features/market/domain/models.dart';
import 'package:zentrix/features/market/presentation/pair_screen.dart';
import 'package:zentrix/features/market/presentation/widgets/candle_chart.dart';
import 'package:zentrix/features/pulse/application/pulse_providers.dart';
import 'package:zentrix/features/pulse/domain/models.dart';
import 'package:zentrix/features/pulse/presentation/pulse_screen.dart';
import 'package:zentrix/features/settings/presentation/profile_button.dart';

import 'helpers.dart';
import 'radar_test.dart' show FakeRadarRepo;

final t0 = DateTime.utc(2026, 11, 15, 12);

Candle candle(int i, double c, {double? v}) => Candle(
  t: t0.add(Duration(minutes: 15 * i)),
  o: c - 1,
  h: c + 2,
  l: c - 3,
  c: c,
  v: v,
);

List<Candle> series(int n) => [for (var i = 0; i < n; i++) candle(i, 100 + i.toDouble(), v: 10 + i.toDouble())];

LiveCandle liveOf(Candle? c, {bool live = true, Candle? closed, bool open = true, DateTime? closesAt}) => LiveCandle(
  symbol: 'BTC/USDT',
  venue: 'binance_spot',
  timeframe: '15m',
  live: live,
  candle: c,
  forming: live,
  closed: closed,
  closesAt: closesAt ?? (open ? DateTime.now().add(const Duration(seconds: 90)) : null),
  marketOpen: open,
  serverTime: DateTime.now(),
  pollS: live ? 2 : 60,
  source: live ? 'binance_spot' : 'stored',
);

NewsItem news(int id, String title, String impact, {int age = 600, List<String> assets = const ['USD']}) => NewsItem(
  id: id,
  source: 'fed',
  sourceName: 'Federal Reserve',
  kind: 'central_bank',
  title: title,
  url: 'https://example.com/$id',
  publishedAt: DateTime.now().subtract(Duration(seconds: age)),
  ageS: age,
  impact: impact,
  impactReason: 'rule',
  assets: assets,
);

final feed = NewsFeed(
  items: [
    news(1, 'Fed holds rates steady', 'high', age: 300),
    news(2, 'Bitcoin slides to 3-month low', 'medium', assets: ['CRYPTO', 'BTC']),
    news(3, 'Gold price forecast: XAU/USD eyes 4,200', 'low', assets: ['XAU', 'USD']),
  ],
  sources: const [
    NewsSource(code: 'fed', name: 'Federal Reserve', kind: 'central_bank', ok: true),
    NewsSource(code: 'ecb', name: 'European Central Bank', kind: 'central_bank', ok: false),
  ],
  updatedAt: DateTime.now().subtract(const Duration(minutes: 2)),
  method: 'rules',
);

CalendarPage calendar() => CalendarPage(
  items: [
    NewsEvent(
      title: 'CPI m/m',
      currency: 'USD',
      impact: 'high',
      eventAt: DateTime.now().add(const Duration(minutes: 40)),
      inS: 2400,
      forecast: '0.3%',
      previous: '0.4%',
    ),
    NewsEvent(
      title: 'ECB President Lagarde Speaks',
      currency: 'EUR',
      impact: 'medium',
      eventAt: DateTime.now().add(const Duration(hours: 3)),
      inS: 10800,
    ),
  ],
  calendarUpdatedAt: DateTime.now(),
);

void main() {
  group('mergeLive', () {
    test('the forming candle replaces the last one with the same open time', () {
      final base = series(3);
      final out = mergeLive(base, liveOf(candle(2, 150)));
      expect(out, hasLength(3));
      expect(out.last.c, 150);
    });

    test('a new period appends; the just-closed candle gets its final values', () {
      final base = series(3);
      final out = mergeLive(base, liveOf(candle(3, 160), closed: candle(2, 140)));
      expect(out.map((c) => c.c), [100, 101, 140, 160]);
    });

    test('a closed-candle feed appends a newly stored close', () {
      final out = mergeLive(series(3), liveOf(candle(3, 103), live: false));
      expect(out, hasLength(4));
      expect(mergeLive(series(3), liveOf(candle(1, 101), live: false)), hasLength(3)); // already there
    });
  });

  test('equity curve: running P&L of closed trades, by close time', () {
    JournalEntry e(int id, double pnl, int day, {bool open = false}) => JournalEntry(
      id: id,
      symbol: 'EUR/USD',
      side: 'long',
      status: open ? 'open' : 'closed',
      quantity: 1,
      entryPrice: 1.1,
      entryAt: DateTime.utc(2026, 11, day),
      exitAt: open ? null : DateTime.utc(2026, 11, day, 12),
      accountCurrency: 'USD',
      pnlAccount: open ? null : pnl,
    );
    expect(equityCurve([e(1, -20, 3), e(2, 50, 1), e(3, 10, 2), e(4, 99, 4, open: true)]), [0, 50, 60, 40]);
  });

  test('Pulse filters map to feed queries', () {
    expect(pulseQuery(PulseFilter.high, null), (impact: 'high', kind: null, asset: null));
    expect(pulseQuery(PulseFilter.centralBanks, 'EUR').kind, 'central_bank');
    expect(pulseQuery(PulseFilter.crypto, null).asset, 'CRYPTO');
    expect(pulseQuery(PulseFilter.crypto, 'BTC').asset, 'BTC'); // a tapped badge narrows further
  });

  testWidgets('live chart: eases to new ticks, appends candles, offers jump-to-latest after panning', (tester) async {
    var candles = series(120);
    late StateSetter set;
    await pumpScreen(
      tester,
      Scaffold(
        body: StatefulBuilder(
          builder: (context, s) {
            set = s;
            return CandleChart(
              candles: candles,
              decimals: 2,
              live: ChartLive(live: true, closesAt: DateTime.now().add(const Duration(minutes: 3))),
              zones: [ChartZone(from: 200, to: 190, color: ZxPalette.dark.bearish)],
            );
          },
        ),
      ),
    );
    set(() => candles = [...candles.sublist(0, 119), candle(119, 230)]); // a tick
    await tester.pump(const Duration(milliseconds: 300));
    set(() => candles = [...candles, candle(120, 231)]); // the next candle opens
    await tester.pump(const Duration(milliseconds: 700));
    expect(tester.takeException(), isNull);

    expect(find.byTooltip('Jump to latest'), findsNothing);
    await tester.drag(find.byType(CandleChart), const Offset(300, 0));
    await tester.pump();
    expect(find.byTooltip('Jump to latest'), findsOneWidget);
    await tester.tap(find.byTooltip('Jump to latest'));
    await tester.pump();
    expect(find.byTooltip('Jump to latest'), findsNothing);
    await tester.pump(const Duration(seconds: 2)); // the countdown keeps ticking without errors
  });

  Future<void> pumpPair(WidgetTester tester, LiveCandle live) async {
    final s = CandleSeries(symbol: 'BTC/USDT', venue: 'binance_spot', timeframe: '15m', candles: series(50));
    await pumpScreen(
      tester,
      const PairScreen(symbol: 'BTC/USDT'),
      reduceMotion: true,
      overrides: [
        candlesProvider.overrideWith((ref, k) async => s),
        liveCandleProvider.overrideWith((ref, k) => Stream.value(live)),
        latestSignalProvider.overrideWith((ref, k) async => null),
        instrumentsProvider.overrideWith((ref) async => const <Instrument>[]),
      ],
    );
    await tester.pump(const Duration(milliseconds: 50));
  }

  testWidgets('pair view says whether the chart is live', (tester) async {
    await pumpPair(tester, liveOf(candle(49, 180)));
    expect(find.text('Live'), findsOneWidget);
    expect(find.text('180.000'), findsWidgets); // the header follows the live candle
    expect(find.text('Signal'), findsOneWidget);
    expect(find.text('Levels'), findsOneWidget);
  });

  testWidgets('pair view: a closed-candle feed is labelled, never shown as live', (tester) async {
    await pumpPair(tester, liveOf(candle(49, 149), live: false));
    expect(find.text('Updates at candle close'), findsOneWidget);
    expect(find.text('Live'), findsNothing);
  });

  testWidgets('pair view: a closed market says so', (tester) async {
    await pumpPair(tester, liveOf(candle(49, 149), live: false, open: false));
    expect(find.text('Market closed'), findsOneWidget);
  });

  testWidgets('Pulse: calendar countdown, breaking item, impact tags, filters and asset badges', (tester) async {
    final container = await pumpScreen(
      tester,
      const PulseScreen(),
      reduceMotion: true,
      overrides: [
        pulseFeedProvider.overrideWith((ref) async => feed),
        pulseCalendarProvider.overrideWith((ref) async => calendar()),
      ],
    );
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.text('Market Pulse'), findsOneWidget);
    expect(find.text('CPI m/m'), findsOneWidget); // the next high-impact event
    expect(find.textContaining('Forecast 0.3%'), findsNothing); // the up-next event shows in the header row
    expect(find.text('BREAKING'), findsOneWidget);
    expect(find.text('Fed holds rates steady'), findsOneWidget);
    expect(find.text('High impact'), findsWidgets);
    expect(find.text('Low impact'), findsOneWidget);
    expect(find.textContaining('1 of 2 sources working'), findsOneWidget);

    await tester.tap(find.descendant(of: find.byType(ZxChipBar<PulseFilter>), matching: find.text('High impact')));
    await tester.pump();
    expect(container.read(pulseFilterProvider), PulseFilter.high);

    await Scrollable.ensureVisible(tester.element(find.text('BTC')), alignment: 0.5);
    await tester.pump();
    await tester.tap(find.text('BTC'));
    await tester.pump();
    expect(container.read(pulseAssetProvider), 'BTC');
    expect(find.text('Showing'), findsOneWidget);
  });

  testWidgets('Home shows the latest headlines and links to the Pulse', (tester) async {
    await pumpScreen(
      tester,
      const DashboardScreen(),
      reduceMotion: true,
      overrides: [
        marketRepositoryProvider.overrideWithValue(FakeRadarRepo()),
        pulseHeadlinesProvider.overrideWith((ref) async => feed),
      ],
    );
    await tester.pump(const Duration(milliseconds: 50));
    await Scrollable.ensureVisible(tester.element(find.text('See all')), alignment: 0.5);
    expect(find.text('Fed holds rates steady'), findsOneWidget);
  });

  testWidgets('the profile button opens Settings', (tester) async {
    final router = GoRouter(
      routes: [
        GoRoute(
          path: '/',
          builder: (_, _) => Scaffold(appBar: AppBar(actions: const [ProfileButton()])),
        ),
        GoRoute(
          path: '/settings',
          builder: (_, _) => const Scaffold(body: Text('settings page')),
        ),
      ],
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [currentUserProvider.overrideWithValue(null)],
        child: MaterialApp.router(
          routerConfig: router,
          theme: zxDarkTheme,
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
        ),
      ),
    );
    await tester.pump();
    await tester.tap(find.byKey(const Key('profileButton')));
    await tester.pumpAndSettle();
    expect(find.text('settings page'), findsOneWidget);
  });

  testWidgets('ladder, equity curve and CI bar render', (tester) async {
    await pumpScreen(
      tester,
      const Scaffold(
        body: Column(
          children: [
            PriceLadder(
              entry: 1.1,
              stop: 1.095,
              target: 1.11,
              decimals: 5,
              entryLabel: 'Entry',
              stopLabel: 'Stop',
              targetLabel: 'Take-profit',
              stopNote: '50 pips',
              targetNote: '2R',
            ),
            EquityChart(values: [0, 50, 60, 40]),
            CiBar(value: 0.52, low: 0.47, high: 0.57),
          ],
        ),
      ),
    );
    expect(tester.takeException(), isNull);
  });
}

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:zentrix/core/format/formatters.dart';
import 'package:zentrix/core/widgets/controls.dart';
import 'package:zentrix/core/widgets/motion.dart';
import 'package:zentrix/features/dashboard/presentation/dashboard_screen.dart';
import 'package:zentrix/features/market/data/market_repository.dart';
import 'package:zentrix/features/market/domain/models.dart';

import 'helpers.dart';

Map<String, dynamic> item(String symbol, String light, {double? price, double? change, int rank = 1}) => {
  'rank': rank,
  'symbol': symbol,
  'display_name': '$symbol name',
  'asset_class': 'fx',
  'venue': 'twelvedata',
  'price_decimals': 5,
  'light': light,
  'reasons': light == 'green' ? <String>[] : ['economic calendar unavailable'],
  'trend_regime': 'trending',
  'trend_direction': 'down',
  'adx': 31.2,
  'volatility_regime': 'high',
  'volatility_percentile': 84.0,
  'news_state': light == 'red' ? 'blackout' : 'clear',
  'next_event': null,
  'next_event_in_s': null,
  'sessions': ['London'],
  'last_price': price,
  'last_candle_close': '2026-11-14T09:00:00Z',
  'change_24h_pct': change,
  'spark': price == null ? <double>[] : [price - 0.001, price + 0.0005, price],
  'spark_from': null,
};

final radarJson = <String, dynamic>{
  'timeframe': '15m',
  'as_of': '2026-11-14T09:01:00Z',
  'ranking': 'conditions first',
  'method': 'rules',
  'items': [
    item('GBP/USD', 'green', price: 1.32390, change: 0.21, rank: 1),
    item('EUR/USD', 'red', price: 1.10572, change: -0.28, rank: 2),
    item('XAU/USD', 'unknown', rank: 3),
  ],
};

Map<String, dynamic> scenarioJson(String symbol, double coverage, List<double> ci) => {
  'symbol': symbol,
  'venue': 'twelvedata',
  'timeframe': '15m',
  'last_close': 1.1,
  'as_of': '2026-11-14T09:00:00Z',
  'method': 'bands',
  'direction': <Object>[],
  'premium': {'feature': 'scenario', 'label': 'Premium'},
  'steps': [
    for (var k = 1; k <= 5; k++)
      {
        'k': k,
        'at': DateTime.utc(2026, 11, 14, 9, 15 * k).toIso8601String(),
        'low': 1.1 - 0.0004 * k,
        'median': 1.1,
        'high': 1.1 + 0.0004 * k,
        'nominal_coverage': 0.8,
        'coverage': coverage,
        'coverage_ci95': ci,
        'coverage_tested': 250,
        'history': 1000,
      },
  ],
};

class FakeRadarRepo extends Fake implements MarketRepository {
  FakeRadarRepo({this.coverage = 0.70, this.ci = const [0.64, 0.76]});

  final double coverage;
  final List<double> ci;
  final List<String> scenarioCalls = [];

  @override
  Future<Radar> radar({String timeframe = '15m'}) async => Radar.fromJson(radarJson);

  @override
  Future<Scenario?> scenario(String symbol, String timeframe, {int steps = 5}) async {
    scenarioCalls.add(symbol);
    return Scenario.fromJson(scenarioJson(symbol, coverage, ci));
  }
}

Future<void> settle(WidgetTester tester) async {
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 50));
}

void main() {
  test('radar and scenario payloads parse (change_24h_pct, nullable prices)', () {
    final r = Radar.fromJson(radarJson);
    expect(r.items.map((i) => i.symbol), ['GBP/USD', 'EUR/USD', 'XAU/USD']);
    expect(r.items[1].change24hPct, -0.28);
    expect(r.items[2].hasData, isFalse);
    final s = Scenario.fromJson(scenarioJson('EUR/USD', 0.77, [0.71, 0.82]));
    expect(s.steps.last.coverage, 0.77);
    expect(s.steps.last.coverageTested, 250);
  });

  testWidgets('Market Radar: focus card, measured range, ranked list, no direction call', (tester) async {
    final repo = FakeRadarRepo();
    await pumpScreen(
      tester,
      const DashboardScreen(),
      reduceMotion: true,
      overrides: [marketRepositoryProvider.overrideWithValue(repo)],
    );
    await settle(tester);

    expect(find.text('Market Radar'), findsOneWidget);
    // the focus market defaults to EUR/USD (hero card) even though it ranks second
    expect(repo.scenarioCalls.last, 'EUR/USD');
    expect(find.text('Stay out'), findsOneWidget);
    // the measured coverage is shown next to the nominal band, flagged when statistically short (CI below 80%)
    expect(find.textContaining('80% band · held 70% of the time in 250 past tests'), findsOneWidget);
    expect(find.byIcon(Icons.warning_amber_rounded), findsOneWidget);
    expect(find.textContaining('Range, not direction'), findsOneWidget);
    // the range reads low to high even inside right-to-left text
    expect(find.text(Fmt.ltr('1.09800 – 1.10200')), findsOneWidget);
    // ranked rows in server order
    final gbp = tester.getTopLeft(find.text('GBP/USD').last).dy;
    final xau = tester.getTopLeft(find.text('XAU/USD').last).dy;
    expect(gbp, lessThan(xau));
    expect(find.text('No live feed yet'), findsOneWidget);
    // the Home never calls a direction
    expect(find.text('Up'), findsNothing);
    expect(find.text('Down'), findsNothing);

    // tapping a row moves the focus card
    await Scrollable.ensureVisible(tester.element(find.text('GBP/USD').last), alignment: 0.5);
    await tester.pump();
    await tester.tap(find.text('GBP/USD').last);
    await settle(tester);
    expect(repo.scenarioCalls.last, 'GBP/USD');
    expect(find.text('Conditions OK'), findsOneWidget);
  });

  testWidgets('a range consistent with its target is not flagged', (tester) async {
    await pumpScreen(
      tester,
      const DashboardScreen(),
      reduceMotion: true,
      overrides: [
        marketRepositoryProvider.overrideWithValue(FakeRadarRepo(coverage: 0.77, ci: [0.71, 0.82])),
      ],
    );
    await settle(tester);
    expect(find.byIcon(Icons.verified_outlined), findsOneWidget);
    expect(find.byIcon(Icons.warning_amber_rounded), findsNothing);
  });

  testWidgets('segmented control reports the tapped value', (tester) async {
    String? picked;
    await pumpScreen(
      tester,
      Scaffold(
        body: ZxSegmented<String>(
          segments: const [('a', 'Alpha'), ('b', 'Beta')],
          selected: 'a',
          onChanged: (v) => picked = v,
        ),
      ),
    );
    await tester.tap(find.text('Beta'));
    expect(picked, 'b');
  });

  testWidgets('reduced motion stops the pulsing orb', (tester) async {
    await pumpScreen(tester, const Scaffold(body: StatusOrb(color: Color(0xFF10B981))), reduceMotion: true);
    await tester.pump();
    expect(tester.binding.hasScheduledFrame, isFalse);
    await pumpScreen(tester, const Scaffold(body: StatusOrb(color: Color(0xFF10B981))));
    await tester.pump();
    expect(tester.binding.hasScheduledFrame, isTrue);
  });
}

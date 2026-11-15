import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:zentrix/core/theme/tokens.dart';
import 'package:zentrix/features/market/application/market_providers.dart';
import 'package:zentrix/features/market/domain/models.dart';
import 'package:zentrix/features/market/presentation/pair_screen.dart';
import 'package:zentrix/features/market/presentation/widgets/candle_chart.dart';

import 'helpers.dart';
import 'live_pulse_test.dart' show candle, liveOf, series;

Instrument instrument(String symbol, String assetClass, List<String> timeframes) => Instrument(
  symbol: symbol,
  displayName: '$symbol name',
  assetClass: assetClass,
  instrumentType: 'spot',
  base: symbol.split('/').first,
  quote: 'USD',
  priceDecimals: 5,
  session: 'fx_24x5',
  active: true,
  listings: const [Listing(venue: 'twelvedata', venueSymbol: 'EUR/USD', status: 'active', isPrimary: true)],
  timeframes: timeframes,
);

final outlookJson = <String, dynamic>{
  'symbol': 'EUR/USD',
  'venue': 'twelvedata',
  'timeframe': '15m',
  'as_of': DateTime.utc(2026, 11, 15, 12, 30).toIso8601String(),
  'last_close': 1.1,
  'atr': 0.0012,
  'label': 'Technical Pattern Projection (based on historical candlestick & ATR behaviour)',
  'pattern': {
    'key': 'hammer',
    'name': 'Hammer (bullish pin bar)',
    'bias': 1,
    'candles': 1,
    'meaning': 'Sellers pushed price down, buyers pulled it back: a long lower wick.',
    'starts': DateTime.utc(2026, 11, 15, 12, 15).toIso8601String(),
    'past_cases': 64,
    'enough_cases': true,
  },
  'structure': {
    'trend_regime': 'ranging',
    'trend_direction': null,
    'adx': 17.5,
    'swing': 'range',
    'rsi': 44.2,
    'momentum_pct': -0.12,
    'lookback': 20,
  },
  'projection': {
    'basis': 'pattern',
    'cases': 64,
    'band': [0.2, 0.8],
    'steps': [
      for (var k = 1; k <= 5; k++)
        {
          'k': k,
          'at': DateTime.utc(2026, 11, 15, 12, 30 + 15 * k).toIso8601String(),
          'open': 1.1 + 0.0001 * (k - 1),
          'high': 1.1 + 0.0001 * k + 0.0004,
          'low': 1.1 - 0.0004,
          'close': 1.1 + 0.0001 * k,
          'band_low': 1.1 - 0.0005 * k,
          'band_high': 1.1 + 0.0006 * k,
        },
    ],
  },
  'base_rate': {
    'horizon': 5,
    'rate': 0.53,
    'ci95': [0.41, 0.65],
    'cases': 62,
    'baseline': 0.5,
    'edge': false,
    'by_step': [
      for (var k = 1; k <= 5; k++)
        {
          'k': k,
          'rate': 0.52,
          'ci95': [0.4, 0.64],
          'cases': 62,
          'baseline': 0.5,
        },
    ],
  },
  'history': 1300,
  'method': 'rules',
  'premium': {'feature': 'pattern_outlook', 'label': 'Premium'},
  'disclaimer': 'Not financial advice.',
};

void main() {
  test('instruments carry their chart timeframes; the chart offers only those', () {
    final fx = instrument('EUR/USD', 'fx', ['15m', '1h', '4h', '1d']);
    expect(availableTimeframes(fx), ['15m', '1h', '4h', '1d']);
    expect(availableTimeframes(null), chartTimeframes);
    expect(availableTimeframes(instrument('AUD/JPY', 'fx', ['1d'])), ['1d']);
    expect(instrument('X/Y', 'fx', []).hasChartData, isFalse);
    expect(timeframeDuration('4h'), const Duration(hours: 4));
    expect(timeframeDuration('1d'), const Duration(days: 1));
    final o = PatternOutlook.fromJson(outlookJson);
    expect(o.pattern!.pastCases, 64);
    expect(o.projection!.steps.last.bandHigh, closeTo(1.103, 1e-9));
    expect(o.hasEdge, isFalse);
  });

  Future<List<String>> pumpPair(WidgetTester tester, Instrument inst, {String tf = '15m'}) async {
    final requested = <String>[];
    await pumpScreen(
      tester,
      PairScreen(symbol: inst.symbol, initialTimeframe: tf),
      reduceMotion: true,
      overrides: [
        instrumentsProvider.overrideWith((ref) async => [inst]),
        candlesProvider.overrideWith((ref, k) async {
          requested.add(k.timeframe);
          return CandleSeries(symbol: inst.symbol, venue: 'twelvedata', timeframe: k.timeframe, candles: series(60));
        }),
        liveCandleProvider.overrideWith((ref, k) => Stream.value(liveOf(candle(59, 159), live: false))),
        latestSignalProvider.overrideWith((ref, k) async => null),
        patternProvider.overrideWith((ref, k) async => PatternOutlook.fromJson(outlookJson)),
      ],
    );
    await tester.pump(const Duration(milliseconds: 50));
    return requested;
  }

  testWidgets('FX: no 5m chip, the reason is shown, and a 5m deep link opens 15m', (tester) async {
    final requested = await pumpPair(tester, instrument('EUR/USD', 'fx', ['15m', '1h', '4h', '1d']), tf: '5m');
    expect(find.text('5m'), findsNothing);
    expect(find.text('4h'), findsOneWidget);
    expect(find.textContaining('5m candles for FX and gold need a paid data feed'), findsOneWidget);
    expect(requested, everyElement('15m'));
  });

  testWidgets('a market without chart data says so instead of an empty chart', (tester) async {
    await pumpPair(tester, instrument('EUR/NOK', 'fx', []));
    expect(find.textContaining('No chart data for this market'), findsOneWidget);
    expect(find.byType(CandleChart), findsNothing);
  });

  testWidgets('daily-only crosses are labelled', (tester) async {
    await pumpPair(tester, instrument('AUD/JPY', 'fx', ['1d']));
    expect(find.textContaining('Daily candles only'), findsOneWidget);
  });

  testWidgets('Pattern tab: labelled projection, base rate against any candle, no edge said plainly', (tester) async {
    await pumpPair(tester, instrument('EUR/USD', 'fx', ['15m', '1h', '4h', '1d']));
    await tester.scrollUntilVisible(find.text('Pattern'), 200, scrollable: find.byType(Scrollable).first);
    await tester.pump();
    await tester.tap(find.text('Pattern'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100)); // the outlook arrives a frame after the tab opens
    await tester.scrollUntilVisible(
      find.text('Hammer (bullish pin bar)'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('Technical Pattern Projection (based on historical candlestick & ATR behaviour)'), findsOneWidget);
    expect(find.text('Hammer (bullish pin bar)'), findsOneWidget);
    expect(find.text('Classic reading: bullish'), findsOneWidget);
    expect(find.textContaining('price was higher 5 candles later in 53% of 62 past cases'), findsOneWidget);
    expect(find.textContaining('Any candle: 50%'), findsOneWidget);
    expect(find.textContaining('No measurable edge here'), findsOneWidget);
    expect(find.textContaining('Not a prediction or a trade signal'), findsOneWidget);
    expect(tester.takeException(), isNull); // the projection is drawn on the chart
  });

  testWidgets('chart draws a projection next to a forming candle without errors', (tester) async {
    final candles = series(80);
    await pumpScreen(
      tester,
      Scaffold(
        body: CandleChart(
          candles: candles,
          decimals: 2,
          projection: ChartProjection(
            anchor: candles[candles.length - 2].t, // the forming candle takes step 1's slot
            color: ZxPalette.dark.neutral,
            label: 'Projection',
            steps: [
              for (var k = 1; k <= 5; k++)
                ProjectedCandle(o: 178 + k / 10, h: 181, l: 176, c: 178.5 + k / 10, bandLow: 170, bandHigh: 186),
            ],
          ),
          highlight: ChartHighlight(
            from: candles[candles.length - 4].t,
            to: candles[candles.length - 2].t,
            label: 'Three White Soldiers',
            color: ZxPalette.dark.accent,
          ),
        ),
      ),
    );
    await tester.pump();
    expect(tester.takeException(), isNull);
  });
}

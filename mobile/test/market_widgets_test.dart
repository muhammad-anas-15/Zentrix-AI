import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:zentrix/core/widgets/surfaces.dart';
import 'package:zentrix/features/market/data/market_repository.dart';
import 'package:zentrix/features/market/domain/models.dart';
import 'package:zentrix/features/market/presentation/pair_screen.dart';
import 'package:zentrix/features/market/presentation/widgets/conditions_card.dart';

import 'helpers.dart';

class FakeGuard extends Fake implements MarketRepository {
  FakeGuard(this.guard);

  final NewsGuard guard;

  @override
  Future<NewsGuard> newsGuard(String symbol) async => guard;
}

Candle candle(DateTime t, double c) => Candle(t: t, o: c, h: c, l: c, c: c);

void main() {
  test('24h change compares the last close with the close 24 hours earlier', () {
    final t0 = DateTime.utc(2026, 11, 12, 12);
    final candles = [for (var i = 0; i <= 8; i++) candle(t0.add(Duration(hours: 4 * i)), 100 + i.toDouble())];
    // last = 108 at +32h; the close at or before +8h is 102
    expect(change24h(candles), closeTo((108 / 102 - 1) * 100, 1e-9));
    expect(change24h(candles.sublist(6)), isNull); // less than 24h loaded
    expect(change24h(const []), isNull);
  });

  testWidgets('a stale calendar never reads as "nothing coming"', (tester) async {
    await pumpScreen(
      tester,
      const Scaffold(body: NewsGuardCard(symbol: 'EUR/USD')),
      overrides: [
        marketRepositoryProvider.overrideWithValue(FakeGuard(const NewsGuard(symbol: 'EUR/USD', state: 'unknown'))),
      ],
    );
    await tester.pumpAndSettle();
    expect(find.text('Calendar unavailable'), findsOneWidget);
    expect(find.textContaining('news risk is unknown'), findsOneWidget);
    expect(find.text('No relevant events this week'), findsNothing);
  });

  testWidgets('a clear calendar with no event says so', (tester) async {
    await pumpScreen(
      tester,
      const Scaffold(body: NewsGuardCard(symbol: 'EUR/USD')),
      overrides: [
        marketRepositoryProvider.overrideWithValue(FakeGuard(const NewsGuard(symbol: 'EUR/USD', state: 'clear'))),
      ],
    );
    await tester.pumpAndSettle();
    expect(find.text('No relevant events this week'), findsOneWidget);
  });

  testWidgets('the wins/losses bar fills its height in proportion', (tester) async {
    await pumpScreen(
      tester,
      const Scaffold(
        body: SizedBox(
          width: 300,
          child: BreakdownBar(left: 2, right: 1, leftColor: Color(0xFF00FF00), rightColor: Color(0xFFFF0000)),
        ),
      ),
    );
    final boxes = tester
        .renderObjectList<RenderBox>(find.descendant(of: find.byType(BreakdownBar), matching: find.byType(ColoredBox)))
        .toList();
    expect(boxes, hasLength(2));
    expect(boxes.map((b) => b.size.height), everyElement(8.0));
    expect(boxes[0].size.width, closeTo(200, 0.5));
    expect(boxes[1].size.width, closeTo(100, 0.5));
  });
}

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:zentrix/core/models/premium.dart';
import 'package:zentrix/core/network/api_exception.dart';
import 'package:zentrix/core/providers.dart';
import 'package:zentrix/core/storage/token_store.dart';
import 'package:zentrix/features/auth/application/session.dart';
import 'package:zentrix/features/auth/data/auth_repository.dart';
import 'package:zentrix/features/auth/domain/models.dart';
import 'package:zentrix/features/auth/presentation/sign_in_screen.dart';
import 'package:zentrix/features/market/data/market_repository.dart';
import 'package:zentrix/features/market/domain/models.dart';
import 'package:zentrix/features/market/presentation/widgets/levels_card.dart';
import 'package:zentrix/features/market/presentation/widgets/signal_card.dart';
import 'package:zentrix/features/risk/data/risk_repository.dart';
import 'package:zentrix/features/risk/domain/models.dart';
import 'package:zentrix/features/risk/presentation/calculator_screen.dart';
import 'package:zentrix/features/settings/presentation/delete_account_screen.dart';

import 'helpers.dart';

Signal signal({String strength = 'Very Weak - Wait', bool edge = false, PremiumBadge? premium}) => Signal(
  id: 1,
  symbol: 'EUR/USD',
  venue: 'twelvedata',
  timeframe: '15m',
  horizon: 1,
  candleTime: DateTime.utc(2026, 11, 13, 9),
  decisionAt: DateTime.utc(2026, 11, 13, 9, 15),
  createdAt: DateTime.utc(2026, 11, 13, 9, 15, 4),
  direction: 'up',
  confidence: 0.54,
  pUp: 0.54,
  strength: strength,
  model: SignalModel(key: 'k', trainedAt: DateTime.utc(2026, 11), hasDemonstratedEdge: edge),
  premium: premium,
);

class FakeMarket extends Fake implements MarketRepository {
  FakeMarket(this.levelsError);

  final ApiException? levelsError;

  @override
  Future<Levels> levels(String symbol, String timeframe, String side) async {
    if (levelsError != null) throw levelsError!;
    return Levels(
      symbol: symbol,
      timeframe: timeframe,
      side: side,
      entry: 1.1,
      slAtr: 1.5,
      stop: 1.098,
      targets: const [
        LevelTarget(
          r: 1,
          price: 1.102,
          baseRate: BaseRate(
            r: 1,
            hitRate: 0.39,
            breakEvenHitRate: 0.5,
            entries: 650,
            targetFirst: 250,
            stopFirst: 380,
            neitherWithinMaxBars: 20,
            maxBars: 50,
          ),
        ),
      ],
      asOf: DateTime.utc(2026, 11, 13, 9, 15),
      method: 'ATR',
    );
  }
}

class FakeRisk extends Fake implements RiskRepository {
  PositionSizeRequest? last;

  @override
  Future<PositionSize> positionSize(PositionSizeRequest request) async {
    last = request;
    return const PositionSize(
      symbol: 'EUR/USD',
      side: 'long',
      accountCurrency: 'USD',
      units: 20000,
      lots: 0.2,
      riskAmount: 20,
      riskPct: 1,
      stopDistance: 0.001,
      stopPips: 10,
      pipValuePerLot: 10,
      pointSize: 0.00001,
      notional: 22000,
      conversionRate: 1,
      warnings: ['Risk 1% of balance'],
    );
  }
}

class FakeAuth extends Fake implements AuthRepository {
  int deletes = 0;

  @override
  Future<void> deleteAccount() async => deletes++;

  @override
  Future<AppUser> me() async => AppUser(
    id: 'u1',
    plan: 'free',
    premiumAccess: true,
    locale: 'en',
    timezone: 'UTC',
    createdAt: DateTime.utc(2026, 11),
    email: 'dev@example.com',
  );
}

class NoGoogle implements GoogleAuthGateway {
  @override
  bool get available => false;

  @override
  Future<String> idToken() => throw UnimplementedError();

  @override
  Future<void> signOut() async {}
}

void main() {
  testWidgets('a signal without an edge is shown honestly: neutral tier and a 50/50 note', (tester) async {
    await pumpScreen(
      tester,
      Scaffold(
        body: SingleChildScrollView(child: SignalCard(signal: signal())),
      ),
    );
    expect(find.text('Very Weak - Wait'), findsOneWidget);
    expect(find.textContaining('no edge out of sample'), findsOneWidget);
    expect(find.text('54.0%'), findsOneWidget);
    expect(find.text('Premium'), findsNothing);
    expect(find.text('Not financial advice.'), findsOneWidget);
  });

  testWidgets('an earned tier has no 50/50 note; premium markets carry the badge', (tester) async {
    await pumpScreen(
      tester,
      Scaffold(
        body: SingleChildScrollView(
          child: SignalCard(
            signal: signal(
              strength: 'Good',
              edge: true,
              premium: const PremiumBadge(feature: 'all_markets'),
            ),
          ),
        ),
      ),
    );
    expect(find.text('Good'), findsOneWidget);
    expect(find.textContaining('no edge'), findsNothing);
    expect(find.text('Premium'), findsOneWidget);
  });

  testWidgets('ATR levels show the base rate next to break-even, labelled Premium', (tester) async {
    await pumpScreen(
      tester,
      const Scaffold(
        body: SingleChildScrollView(
          child: LevelsCard(symbol: 'EUR/USD', timeframe: '15m', side: 'long'),
        ),
      ),
      overrides: [marketRepositoryProvider.overrideWithValue(FakeMarket(null))],
    );
    await tester.pumpAndSettle();
    expect(find.text('Premium'), findsOneWidget);
    expect(find.textContaining('39.0%'), findsOneWidget);
    expect(find.textContaining('50.0%'), findsOneWidget);
  });

  testWidgets('when the server enforces premium, a locked feature says so with nothing to buy', (tester) async {
    const locked = ApiException(
      status: 403,
      code: 'premium_required',
      message: 'Premium feature',
      details: {'feature': 'trade_levels'},
    );
    await pumpScreen(
      tester,
      const Scaffold(
        body: SingleChildScrollView(
          child: LevelsCard(symbol: 'EUR/USD', timeframe: '15m', side: 'long'),
        ),
      ),
      overrides: [marketRepositoryProvider.overrideWithValue(FakeMarket(locked))],
    );
    await tester.pumpAndSettle();
    expect(find.textContaining('is not on your plan'), findsOneWidget);
    expect(find.textContaining('Purchases are not available'), findsOneWidget);
  });

  testWidgets('position-size calculator validates and shows the result', (tester) async {
    final risk = FakeRisk();
    await pumpScreen(tester, const CalculatorScreen(), overrides: [riskRepositoryProvider.overrideWithValue(risk)]);
    await tester.tap(find.byKey(const Key('calculate')));
    await tester.pump();
    expect(find.text('Required'), findsWidgets); // guests must give a balance, entry and stop
    expect(risk.last, isNull);

    await tester.enterText(find.byKey(const Key('balance')), '2000');
    await tester.enterText(find.byKey(const Key('entry')), '1.1');
    await tester.enterText(find.byKey(const Key('stop')), '1.099');
    await tester.tap(find.byKey(const Key('calculate')));
    await tester.pumpAndSettle();
    expect(risk.last!.balance, 2000);
    expect(risk.last!.riskPct, 1);
    expect(find.byKey(const Key('sizeHeadline')), findsOneWidget);
    expect(find.text('0.20 Lots'), findsOneWidget);
    expect(find.textContaining('Risk 1% of balance', skipOffstage: false), findsOneWidget);
  });

  testWidgets('account deletion needs the typed confirmation, then ends the session', (tester) async {
    final auth = FakeAuth();
    final container = await pumpScreen(
      tester,
      const DeleteAccountScreen(),
      overrides: [authRepositoryProvider.overrideWithValue(auth), googleAuthProvider.overrideWithValue(NoGoogle())],
      tokens: MemoryTokenStore(const Tokens(access: 'a', refresh: 'r')),
    );
    container.read(sessionProvider); // restore the saved session
    await tester.pumpAndSettle();
    expect(container.read(sessionProvider), isA<SessionSignedIn>());
    final button = find.byKey(const Key('confirmDeleteButton'));
    expect(tester.widget<FilledButton>(button).onPressed, isNull);
    await tester.enterText(find.byKey(const Key('confirmDelete')), 'DELETE');
    await tester.pump();
    expect(tester.widget<FilledButton>(button).onPressed, isNotNull);
    await tester.tap(button);
    await tester.pumpAndSettle();
    expect(auth.deletes, 1);
    final s = container.read(sessionProvider);
    expect(s, isA<SessionSignedOut>().having((x) => x.reason, 'reason', SignedOutReason.deleted));
    expect(await container.read(tokenStoreProvider).read(), isNull);
  });

  testWidgets('Urdu lays the app out right-to-left', (tester) async {
    await pumpScreen(
      tester,
      const SignInScreen(),
      locale: const Locale('ur'),
      overrides: [googleAuthProvider.overrideWithValue(NoGoogle())],
    );
    await tester.pumpAndSettle();
    expect(Directionality.of(tester.element(find.byType(SignInScreen))), TextDirection.rtl);
    expect(find.text('منصوبے کے ساتھ ٹریڈ کریں'), findsOneWidget);
  });
}

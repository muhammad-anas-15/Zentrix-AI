import 'package:flutter_test/flutter_test.dart';
import 'package:zentrix/features/alerts/domain/models.dart';
import 'package:zentrix/features/auth/domain/models.dart';
import 'package:zentrix/features/market/domain/models.dart';
import 'package:zentrix/features/risk/domain/models.dart';
import 'package:zentrix/features/track_record/domain/models.dart';

/// Payloads shaped exactly like the backend's (docs/openapi.json), including fields the app ignores.
void main() {
  test('signal with outcome and premium label', () {
    final s = Signal.fromJson({
      'id': 7,
      'symbol': 'USD/JPY',
      'venue': 'twelvedata',
      'timeframe': '15m',
      'horizon': 1,
      'candle_time': '2026-11-13T09:00:00Z',
      'decision_at': '2026-11-13T09:15:00Z',
      'created_at': '2026-11-13T09:15:04.123456Z',
      'direction': 'down',
      'confidence': 0.53,
      'p_up': 0.47,
      'strength': 'Very Weak - Wait',
      'model': {'key': 'USD_JPY_15m_h1', 'trained_at': '2026-11-12T10:00:00Z', 'has_demonstrated_edge': false},
      'backtest_tier': {'ci95': null, 'correct': 0, 'n': 0, 'rate': null, 'share': 0.0},
      'outcome': {
        'outcome': 'win',
        'entry_time': '2026-11-13T09:15:00Z',
        'entry_price': 151.2,
        'exit_time': null,
        'exit_price': 151.1,
        'move_pct': -0.066,
        'resolved_at': '2026-11-13T09:31:00Z',
        'note': null,
      },
      'premium': {'feature': 'all_markets', 'label': 'Premium'},
    });
    expect(s.isUp, isFalse);
    expect(s.isActionable, isFalse); // no edge: never treated as evidence
    expect(s.outcome!.outcome, 'win');
    expect(s.premium!.feature, 'all_markets');
    expect(s.createdAt.isUtc, isTrue);
  });

  test('conditions keep factor values of any type', () {
    final c = Conditions.fromJson({
      'symbol': 'EUR/USD',
      'venue': 'twelvedata',
      'timeframe': '15m',
      'light': 'amber',
      'factors': [
        {'name': 'market', 'status': 'ok', 'value': 'open', 'detail': 'FX market open'},
        {
          'name': 'data',
          'status': 'ok',
          'value': {'age_s': 42},
          'detail': '',
        },
        {
          'name': 'session',
          'status': 'info',
          'value': ['London'],
          'detail': 'London',
        },
      ],
      'trend': {'regime': 'trending'},
      'volatility': {'regime': 'high', 'percentile': 84.2},
      'sessions': ['London'],
      'last_candle_close': '2026-11-13T09:15:00Z',
      'method': 'rules',
      'disclaimer': 'Not financial advice.',
    });
    expect(c.factors[1].value, {'age_s': 42});
    expect(c.volatility['percentile'], 84.2);
  });

  test('position size with integer numbers and locked premium parts', () {
    final p = PositionSize.fromJson({
      'symbol': 'EUR/USD',
      'side': 'long',
      'account_currency': 'USD',
      'units': 20000,
      'lots': 0.2,
      'contract_size': 100000,
      'risk_amount': 20,
      'risk_pct': 1,
      'stop_distance': 0.001,
      'stop_pips': 10,
      'stop_atr': null,
      'pip_size': 0.0001,
      'pip_value_per_lot': 10,
      'point_size': 0.00001,
      'reward_amount': null,
      'risk_reward': null,
      'notional': 22000,
      'margin': null,
      'conversion_rate': 1,
      'conversion_notes': ['quote currency = account currency'],
      'daily_loss_left': null,
      'warnings': [],
      'premium_locked': ['risk_guard'],
      'disclaimer': 'x',
    });
    expect(p.units, 20000.0);
    expect(p.premiumLocked, ['risk_guard']);
    final req = const PositionSizeRequest(symbol: 'EUR/USD', entry: 1.1, stop: 1.099).toJson();
    expect(req, {'symbol': 'EUR/USD', 'entry': 1.1, 'stop': 1.099, 'timeframe': '15m'}); // nulls are omitted
  });

  test('watchlist quotes map change_24h_pct', () {
    final q = Quotes.fromJson({
      'watchlist_id': 1,
      'items': [
        {
          'symbol': 'EUR/USD',
          'display_name': 'Euro / US Dollar',
          'price': 1.0845,
          'as_of': '2026-11-13T09:15:00Z',
          'change_24h_pct': -0.21,
          'news_state': 'clear',
          'next_event': 'USD CPI',
          'next_event_in_s': 3600,
          'latest_signal': null,
        },
      ],
      'premium_locked': [],
      'note': 'Prices are the last closed candle',
    });
    expect(q.items.single.change24hPct, -0.21);
  });

  test('access and track record', () {
    final a = Access.fromJson({
      'plan': 'free',
      'source': null,
      'premium_until': null,
      'premium_access': true,
      'enforced': false,
      'free_markets': {
        'symbols': ['EUR/USD'],
        'timeframes': ['15m'],
      },
      'features': [
        {'key': 'scenario', 'tier': 'premium', 'available': true, 'via': 'open', 'until': null},
      ],
    });
    expect(a.features.single.via, 'open');
    final t = TrackRecord.fromJson({
      'overall': {
        'signals': 55,
        'pending': 12,
        'decided': 40,
        'wins': 23,
        'losses': 17,
        'flats': 2,
        'voids': 1,
        'hit_rate': 0.575,
        'ci95': [0.42, 0.72],
      },
      'by_strength': [
        {
          'strength': 'Very Weak - Wait',
          'signals': 55,
          'pending': 12,
          'decided': 40,
          'wins': 23,
          'losses': 17,
          'flats': 2,
          'voids': 1,
          'hit_rate': 0.575,
          'ci95': null,
        },
      ],
      'filters': {},
      'first_signal_at': null,
      'last_signal_at': null,
    });
    expect(t.overall.ci95, [0.42, 0.72]);
    expect(t.byStrength.single.strength, 'Very Weak - Wait');
  });
}

import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:zentrix/core/format/formatters.dart';

void main() {
  test('prices get sensible decimals and grouping', () {
    expect(Fmt.price(1.084567), '1.08457');
    expect(Fmt.price(151.2349), '151.235');
    expect(Fmt.price(2654.1), '2,654.10');
    expect(Fmt.price(97250.5), '97,250.50');
    expect(Fmt.price(1.1, decimals: 2), '1.10');
    expect(Fmt.price(null), Fmt.dash);
  });

  test('percent, money and countdown', () {
    expect(Fmt.ratio(0.5432), '54.3%');
    expect(Fmt.signedPercent(1.234), Fmt.ltr('+1.23%'));
    expect(Fmt.signedPercent(-0.5), Fmt.ltr('-0.50%'));
    expect(Fmt.money(-12.5, 'USD'), Fmt.ltr('-12.50 USD'));
    expect(Fmt.money(1200, 'EUR', signed: true), Fmt.ltr('+1,200.00 EUR'));
    expect(Fmt.countdown(3900), '1h 05m');
    expect(Fmt.countdown(754), '12m 34s');
    expect(Fmt.countdown(-3), '0s');
  });

  test('signed numbers stay left-to-right inside Urdu text', () {
    final s = Fmt.signedPercent(-0.28);
    expect(s.codeUnitAt(0), 0x2066); // LRI
    expect(s.codeUnitAt(s.length - 1), 0x2069); // PDI
    expect(s.substring(1, s.length - 1), '-0.28%');
  });

  test('dates format in Urdu too', () async {
    await initializeDateFormatting('ur');
    final t = DateTime.utc(2026, 11, 14, 9, 5);
    expect(Fmt.dateTime(t, 'en'), isNotEmpty);
    expect(Fmt.dateTime(t, 'ur'), isNotEmpty);
  });
}

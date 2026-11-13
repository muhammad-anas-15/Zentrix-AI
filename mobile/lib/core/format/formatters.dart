import 'package:intl/intl.dart';

/// Number, price, percent, money and time formatting. Prices keep Latin digits in every locale so they
/// read the same as on any trading platform.
abstract final class Fmt {
  static const _numberLocale = 'en_US';
  static const dash = '—';

  /// Keeps a signed number intact inside right-to-left (Urdu) text: "-0.28%", not "%0.28-".
  /// The isolate characters (LRI ... PDI) are invisible.
  static String ltr(String s) => '\u2066$s\u2069';

  /// Decimals for a price when the instrument's `price_decimals` is not at hand.
  static int guessDecimals(double price) {
    final a = price.abs();
    if (a >= 1000) return 2;
    if (a >= 100) return 3;
    if (a >= 10) return 4;
    return 5;
  }

  static String price(double? v, {int? decimals}) {
    if (v == null || v.isNaN) return dash;
    final d = decimals ?? guessDecimals(v);
    return NumberFormat.decimalPatternDigits(locale: _numberLocale, decimalDigits: d).format(v);
  }

  static String number(double? v, {int decimals = 2}) {
    if (v == null || v.isNaN) return dash;
    return NumberFormat.decimalPatternDigits(locale: _numberLocale, decimalDigits: decimals).format(v);
  }

  /// A ratio as a percent: 0.543 -> "54.3%".
  static String ratio(double? v, {int decimals = 1}) {
    if (v == null || v.isNaN) return dash;
    return '${(v * 100).toStringAsFixed(decimals)}%';
  }

  /// A value already in percent, with its sign: 1.234 -> "+1.23%".
  static String signedPercent(double? pct, {int decimals = 2}) {
    if (pct == null || pct.isNaN) return dash;
    final s = pct.toStringAsFixed(decimals);
    return ltr(pct > 0 ? '+$s%' : '$s%');
  }

  static String money(double? v, String currency, {int decimals = 2, bool signed = false}) {
    if (v == null || v.isNaN) return dash;
    final n = NumberFormat.decimalPatternDigits(locale: _numberLocale, decimalDigits: decimals).format(v.abs());
    final sign = v < 0 ? '-' : (signed && v > 0 ? '+' : '');
    return ltr('$sign$n $currency');
  }

  /// Seconds as "2h 05m", "12m 30s" or "45s".
  static String countdown(int seconds) {
    final s = seconds < 0 ? 0 : seconds;
    final h = s ~/ 3600;
    final m = (s % 3600) ~/ 60;
    final sec = s % 60;
    if (h > 0) return '${h}h ${m.toString().padLeft(2, '0')}m';
    if (m > 0) return '${m}m ${sec.toString().padLeft(2, '0')}s';
    return '${sec}s';
  }

  /// Local date and time, e.g. "14 Nov, 13:05".
  static String dateTime(DateTime t, String locale) => DateFormat('d MMM, HH:mm', locale).format(t.toLocal());

  static String time(DateTime t, String locale) => DateFormat('HH:mm', locale).format(t.toLocal());
}

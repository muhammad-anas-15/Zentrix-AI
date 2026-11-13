import 'dart:io';
import 'dart:math' as math;

import 'package:flutter/painting.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:zentrix/core/theme/tokens.dart';

double _luminance(Color c) {
  double channel(double v) => v <= 0.03928 ? v / 12.92 : math.pow((v + 0.055) / 1.055, 2.4).toDouble();
  return 0.2126 * channel(c.r) + 0.7152 * channel(c.g) + 0.0722 * channel(c.b);
}

/// WCAG contrast ratio of an opaque foreground on an opaque background.
double contrast(Color a, Color b) {
  final la = _luminance(a);
  final lb = _luminance(b);
  return (math.max(la, lb) + 0.05) / (math.min(la, lb) + 0.05);
}

void main() {
  group('palettes are readable', () {
    for (final (name, p) in [('dark', ZxPalette.dark), ('light', ZxPalette.light)]) {
      test('$name: text and semantic colours meet WCAG contrast on the page and surfaces', () {
        for (final bg in [p.background, p.surface, p.surfaceRaised]) {
          expect(contrast(p.textPrimary, bg), greaterThanOrEqualTo(7), reason: 'primary text');
          expect(contrast(p.textSecondary, bg), greaterThanOrEqualTo(4.5), reason: 'secondary text');
          expect(contrast(p.textMuted, bg), greaterThanOrEqualTo(3), reason: 'captions');
          for (final c in [p.bullish, p.bearish, p.caution, p.gold, p.accent, p.neutral]) {
            expect(contrast(c, bg), greaterThanOrEqualTo(3), reason: 'semantic $c on $bg');
          }
        }
        expect(contrast(p.textOnAccent, p.accent), greaterThanOrEqualTo(4.5), reason: 'button label');
      });
    }
  });

  test('screens use tokens only: no raw colours or font sizes outside lib/core/theme', () {
    final offenders = <String>[];
    final pattern = RegExp(r'Color\(0x|Colors\.|fontSize:');
    for (final f in Directory('lib').listSync(recursive: true).whereType<File>()) {
      final path = f.path.replaceAll(r'\', '/');
      if (!path.endsWith('.dart') || path.contains('/core/theme/') || path.contains('/l10n/gen/')) continue;
      if (path.endsWith('.g.dart') || path.endsWith('.freezed.dart')) continue;
      final lines = f.readAsLinesSync();
      for (var i = 0; i < lines.length; i++) {
        if (pattern.hasMatch(lines[i])) offenders.add('$path:${i + 1}: ${lines[i].trim()}');
      }
    }
    expect(offenders, isEmpty);
  });
}

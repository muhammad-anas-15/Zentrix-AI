import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../../../core/theme/tokens.dart';

/// Minimal line chart of closes (with a soft fill), for ticker tiles.
class Sparkline extends StatelessWidget {
  const Sparkline({super.key, required this.values, required this.color});

  final List<double> values;
  final Color color;

  @override
  Widget build(BuildContext context) => Directionality(
    textDirection: TextDirection.ltr,
    child: CustomPaint(painter: _SparkPainter(values, color), size: Size.infinite),
  );
}

class _SparkPainter extends CustomPainter {
  _SparkPainter(this.values, this.color);

  final List<double> values;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    if (values.length < 2) return;
    final lo = values.reduce(math.min);
    final hi = values.reduce(math.max);
    final span = hi - lo == 0 ? 1.0 : hi - lo;
    final path = Path();
    for (var i = 0; i < values.length; i++) {
      final x = size.width * i / (values.length - 1);
      final y = size.height - (values[i] - lo) / span * size.height;
      i == 0 ? path.moveTo(x, y) : path.lineTo(x, y);
    }
    final fill = Path.from(path)
      ..lineTo(size.width, size.height)
      ..lineTo(0, size.height)
      ..close();
    canvas
      ..drawPath(
        fill,
        Paint()
          ..shader = LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [color.withValues(alpha: 0.25), color.withValues(alpha: 0)],
          ).createShader(Offset.zero & size),
      )
      ..drawPath(
        path,
        Paint()
          ..color = color
          ..style = PaintingStyle.stroke
          ..strokeWidth = ZxSize.hairline * 1.5,
      );
  }

  @override
  bool shouldRepaint(_SparkPainter old) => old.values != values || old.color != color;
}

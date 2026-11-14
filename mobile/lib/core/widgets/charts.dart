import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../format/formatters.dart';
import '../theme/theme.dart';
import '../theme/tokens.dart';

/// Smoothed line of closes with a gradient fill and a glowing last point. Always left-to-right.
class AreaChart extends StatelessWidget {
  const AreaChart({super.key, required this.values, required this.color, this.showLastDot = true});

  final List<double> values;
  final Color color;
  final bool showLastDot;

  @override
  Widget build(BuildContext context) => Directionality(
    textDirection: TextDirection.ltr,
    child: CustomPaint(
      size: Size.infinite,
      painter: _AreaPainter(values, color, showLastDot, context.zx.palette.textOnAccent),
    ),
  );
}

class _AreaPainter extends CustomPainter {
  _AreaPainter(this.values, this.color, this.showLastDot, this.core);

  final List<double> values;
  final Color color;
  final bool showLastDot;
  final Color core;

  @override
  void paint(Canvas canvas, Size size) {
    if (values.length < 2 || size.isEmpty) return;
    final lo = values.reduce(math.min);
    final hi = values.reduce(math.max);
    final span = hi - lo == 0 ? 1.0 : hi - lo;
    final pad = size.height * 0.12;
    final pts = [
      for (var i = 0; i < values.length; i++)
        Offset(size.width * i / (values.length - 1), pad + (size.height - 2 * pad) * (1 - (values[i] - lo) / span)),
    ];
    final line = Path()..moveTo(pts.first.dx, pts.first.dy);
    for (var i = 1; i < pts.length; i++) {
      final mid = Offset((pts[i - 1].dx + pts[i].dx) / 2, (pts[i - 1].dy + pts[i].dy) / 2);
      line.quadraticBezierTo(pts[i - 1].dx, pts[i - 1].dy, mid.dx, mid.dy);
    }
    line.lineTo(pts.last.dx, pts.last.dy);
    final fill = Path.from(line)
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
            colors: [color.withValues(alpha: 0.32), color.withValues(alpha: 0)],
          ).createShader(Offset.zero & size),
      )
      ..drawPath(
        line,
        Paint()
          ..color = color
          ..style = PaintingStyle.stroke
          ..strokeWidth = ZxSize.hairline * 2
          ..strokeCap = StrokeCap.round
          ..strokeJoin = StrokeJoin.round,
      );
    if (showLastDot) {
      canvas
        ..drawCircle(
          pts.last,
          ZxSpace.sm,
          Paint()
            ..color = color.withValues(alpha: 0.35)
            ..maskFilter = const MaskFilter.blur(BlurStyle.normal, ZxSpace.sm / 2),
        )
        ..drawCircle(pts.last, ZxSpace.xs - 1, Paint()..color = core)
        ..drawCircle(
          pts.last,
          ZxSpace.xs - 1,
          Paint()
            ..color = color
            ..style = PaintingStyle.stroke
            ..strokeWidth = ZxSize.hairline * 1.5,
        );
    }
  }

  @override
  bool shouldRepaint(_AreaPainter old) => old.values != values || old.color != color;
}

/// A ring that empties as a deadline approaches, with [child] in the middle.
class CountdownRing extends StatelessWidget {
  const CountdownRing({super.key, required this.fraction, required this.color, required this.child});

  /// 1 = the whole window remains, 0 = now.
  final double fraction;
  final Color color;
  final Widget child;

  @override
  Widget build(BuildContext context) => SizedBox.square(
    dimension: ZxSize.ring,
    child: CustomPaint(
      painter: _RingPainter(fraction.clamp(0, 1).toDouble(), color, context.zx.palette.glassStrong),
      child: Center(child: child),
    ),
  );
}

class _RingPainter extends CustomPainter {
  _RingPainter(this.fraction, this.color, this.track);

  final double fraction;
  final Color color;
  final Color track;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    final arc = rect.deflate(ZxSize.ringStroke / 2);
    canvas.drawArc(
      arc,
      0,
      math.pi * 2,
      false,
      Paint()
        ..color = track
        ..style = PaintingStyle.stroke
        ..strokeWidth = ZxSize.ringStroke,
    );
    if (fraction <= 0) return;
    canvas.drawArc(
      arc,
      -math.pi / 2,
      math.pi * 2 * fraction,
      false,
      Paint()
        ..shader = SweepGradient(
          startAngle: -math.pi / 2,
          endAngle: math.pi * 1.5,
          colors: [color.withValues(alpha: 0.4), color],
          transform: const GradientRotation(-math.pi / 2),
        ).createShader(rect)
        ..style = PaintingStyle.stroke
        ..strokeWidth = ZxSize.ringStroke
        ..strokeCap = StrokeCap.round,
    );
  }

  @override
  bool shouldRepaint(_RingPainter old) => old.fraction != fraction || old.color != color;
}

/// One step of an expected-range band.
typedef RangeStep = ({double? low, double? median, double? high});

/// "Fan" of where price may be over the next steps: a band widening from the last close. Range, not direction.
class RangeFan extends StatelessWidget {
  const RangeFan({super.key, required this.lastClose, required this.steps, required this.decimals});

  final double lastClose;
  final List<RangeStep> steps;
  final int decimals;

  @override
  Widget build(BuildContext context) {
    final zx = context.zx;
    return Directionality(
      textDirection: TextDirection.ltr,
      child: SizedBox(
        height: ZxSize.fanChartHeight,
        child: CustomPaint(
          size: Size.infinite,
          painter: _FanPainter(
            lastClose: lastClose,
            steps: steps,
            decimals: decimals,
            band: zx.palette.accent,
            mid: zx.palette.textSecondary,
            grid: zx.palette.chartGrid,
            label: zx.text.chartLabel,
          ),
        ),
      ),
    );
  }
}

class _FanPainter extends CustomPainter {
  _FanPainter({
    required this.lastClose,
    required this.steps,
    required this.decimals,
    required this.band,
    required this.mid,
    required this.grid,
    required this.label,
  });

  final double lastClose;
  final List<RangeStep> steps;
  final int decimals;
  final Color band;
  final Color mid;
  final Color grid;
  final TextStyle label;

  @override
  void paint(Canvas canvas, Size size) {
    final valid = [
      for (final s in steps)
        if (s.low != null && s.high != null) s,
    ];
    if (valid.isEmpty) return;
    final lo = math.min(lastClose, valid.map((s) => s.low!).reduce(math.min));
    final hi = math.max(lastClose, valid.map((s) => s.high!).reduce(math.max));
    final span = hi - lo == 0 ? 1.0 : hi - lo;
    const labelWidth = ZxSize.chartAxisWidth;
    final w = size.width - labelWidth;
    final pad = size.height * 0.1;
    double y(double v) => pad + (size.height - 2 * pad) * (1 - (v - lo) / span);
    double x(int k) => w * k / valid.length;

    final gridPaint = Paint()
      ..color = grid
      ..strokeWidth = ZxSize.hairline;
    for (var k = 0; k <= valid.length; k++) {
      canvas.drawLine(Offset(x(k), pad), Offset(x(k), size.height - pad), gridPaint);
    }

    final upper = Path()..moveTo(0, y(lastClose));
    final lower = <Offset>[];
    for (var k = 0; k < valid.length; k++) {
      upper.lineTo(x(k + 1), y(valid[k].high!));
      lower.add(Offset(x(k + 1), y(valid[k].low!)));
    }
    for (final pt in lower.reversed) {
      upper.lineTo(pt.dx, pt.dy);
    }
    upper.close();
    canvas.drawPath(
      upper,
      Paint()
        ..shader = LinearGradient(
          colors: [band.withValues(alpha: 0.10), band.withValues(alpha: 0.32)],
        ).createShader(Rect.fromLTWH(0, 0, w, size.height)),
    );
    final edge = Paint()
      ..color = band.withValues(alpha: 0.8)
      ..style = PaintingStyle.stroke
      ..strokeWidth = ZxSize.hairline * 1.5;
    final top = Path()..moveTo(0, y(lastClose));
    final bottom = Path()..moveTo(0, y(lastClose));
    for (var k = 0; k < valid.length; k++) {
      top.lineTo(x(k + 1), y(valid[k].high!));
      bottom.lineTo(x(k + 1), y(valid[k].low!));
    }
    canvas
      ..drawPath(top, edge)
      ..drawPath(bottom, edge);

    // median path, dashed
    final medPaint = Paint()
      ..color = mid.withValues(alpha: 0.7)
      ..strokeWidth = ZxSize.hairline;
    var prev = Offset(0, y(lastClose));
    for (var k = 0; k < valid.length; k++) {
      final m = valid[k].median;
      if (m == null) continue;
      final next = Offset(x(k + 1), y(m));
      _dash(canvas, prev, next, medPaint);
      prev = next;
    }
    canvas
      ..drawCircle(Offset(0, y(lastClose)), ZxSpace.xs, Paint()..color = band)
      ..drawCircle(
        Offset(0, y(lastClose)),
        ZxSpace.sm,
        Paint()
          ..color = band.withValues(alpha: 0.3)
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, ZxSpace.xs),
      );
    final last = valid.last;
    _label(canvas, Fmt.price(last.high, decimals: decimals), Offset(w + ZxSpace.xs, y(last.high!)));
    _label(canvas, Fmt.price(last.low, decimals: decimals), Offset(w + ZxSpace.xs, y(last.low!)));
  }

  void _dash(Canvas canvas, Offset a, Offset b, Paint paint) {
    final d = (b - a).distance;
    if (d == 0) return;
    final dir = (b - a) / d;
    for (var t = 0.0; t < d; t += ZxSpace.sm) {
      canvas.drawLine(a + dir * t, a + dir * math.min(t + ZxSpace.xs, d), paint);
    }
  }

  void _label(Canvas canvas, String text, Offset at) {
    final tp = TextPainter(
      text: TextSpan(text: text, style: label),
      textDirection: TextDirection.ltr,
    )..layout();
    tp.paint(canvas, Offset(at.dx, at.dy - tp.height / 2));
  }

  @override
  bool shouldRepaint(_FanPainter old) => old.steps != steps || old.lastClose != lastClose || old.band != band;
}

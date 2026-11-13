import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../../../core/format/formatters.dart';
import '../../../../core/l10n.dart';
import '../../../../core/theme/theme.dart';
import '../../../../core/theme/tokens.dart';
import '../../domain/models.dart';

/// A horizontal price line drawn over the chart (entry, stop, targets).
@immutable
class ChartLevel {
  const ChartLevel({required this.price, required this.label, required this.color});

  final double price;
  final String label;
  final Color color;
}

/// Interactive candlestick chart: drag to pan, pinch to zoom, long-press for the crosshair.
/// Charts read left to right in every locale, so the chart is always laid out LTR.
class CandleChart extends StatefulWidget {
  const CandleChart({super.key, required this.candles, this.decimals, this.levels = const []});

  final List<Candle> candles;
  final int? decimals;
  final List<ChartLevel> levels;

  static const int minVisible = 20;
  static const int initialVisible = 80;

  @override
  State<CandleChart> createState() => _CandleChartState();
}

class _CandleChartState extends State<CandleChart> {
  int _visible = CandleChart.initialVisible;
  double _offset = 0; // candles hidden at the right end (panned back in time)
  int _visibleAtScaleStart = CandleChart.initialVisible;
  int? _cross;

  int get _count => widget.candles.length;

  int _clampVisible(int v) => v.clamp(math.min(CandleChart.minVisible, _count), math.max(_count, 1));

  @override
  void didUpdateWidget(CandleChart old) {
    super.didUpdateWidget(old);
    if (old.candles.length != widget.candles.length) {
      _offset = 0;
      _cross = null;
    }
  }

  ({int start, int end}) _window() {
    final visible = _clampVisible(_visible);
    final end = (_count - _offset.round()).clamp(visible, _count);
    return (start: math.max(0, end - visible), end: end);
  }

  void _setCross(Offset local, double width) {
    final w = _window();
    final plotWidth = width - ZxSize.chartAxisWidth;
    if (plotWidth <= 0 || w.end <= w.start) return;
    final step = plotWidth / (w.end - w.start);
    final i = w.start + (local.dx / step).floor();
    setState(() => _cross = i.clamp(w.start, w.end - 1));
  }

  @override
  Widget build(BuildContext context) {
    final zx = context.zx;
    if (_count == 0) {
      return SizedBox(
        height: ZxSize.chartHeight,
        child: Center(child: Text(context.l10n.noDataForTimeframe, style: zx.text.secondary)),
      );
    }
    final decimals = widget.decimals ?? Fmt.guessDecimals(widget.candles.last.c);
    return Directionality(
      textDirection: TextDirection.ltr,
      child: LayoutBuilder(
        builder: (context, constraints) {
          final w = _window();
          final cross = _cross;
          return SizedBox(
            height: ZxSize.chartHeight,
            child: GestureDetector(
              onScaleStart: (_) => _visibleAtScaleStart = _clampVisible(_visible),
              onScaleUpdate: (d) => setState(() {
                if (d.pointerCount > 1) {
                  _visible = _clampVisible((_visibleAtScaleStart / d.scale).round());
                } else {
                  final plotWidth = constraints.maxWidth - ZxSize.chartAxisWidth;
                  final step = plotWidth / math.max(1, w.end - w.start);
                  _offset = (_offset + d.focalPointDelta.dx / step).clamp(0, math.max(0, _count - _visible)).toDouble();
                }
              }),
              onLongPressStart: (d) => _setCross(d.localPosition, constraints.maxWidth),
              onLongPressMoveUpdate: (d) => _setCross(d.localPosition, constraints.maxWidth),
              onLongPressEnd: (_) => setState(() => _cross = null),
              child: Stack(
                children: [
                  Positioned.fill(
                    child: CustomPaint(
                      painter: _CandlePainter(
                        candles: widget.candles,
                        start: w.start,
                        end: w.end,
                        decimals: decimals,
                        levels: widget.levels,
                        cross: cross,
                        palette: zx.palette,
                        labelStyle: zx.text.chartLabel,
                      ),
                    ),
                  ),
                  if (cross != null)
                    PositionedDirectional(
                      top: ZxSpace.xs,
                      start: ZxSpace.xs,
                      child: _Readout(candle: widget.candles[cross], decimals: decimals),
                    ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}

class _Readout extends StatelessWidget {
  const _Readout({required this.candle, required this.decimals});

  final Candle candle;
  final int decimals;

  @override
  Widget build(BuildContext context) {
    final zx = context.zx;
    String f(double v) => Fmt.price(v, decimals: decimals);
    return DecoratedBox(
      decoration: BoxDecoration(
        color: zx.palette.surfaceRaised,
        borderRadius: BorderRadius.circular(ZxRadius.sm),
        border: Border.all(color: zx.palette.glassBorder, width: ZxSize.hairline),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: ZxSpace.sm, vertical: ZxSpace.xs),
        child: Text(
          '${Fmt.dateTime(candle.t, context.localeCode)}  '
          'O ${f(candle.o)}  H ${f(candle.h)}  L ${f(candle.l)}  C ${f(candle.c)}',
          style: zx.text.chartLabel.copyWith(color: zx.palette.textPrimary),
        ),
      ),
    );
  }
}

class _CandlePainter extends CustomPainter {
  _CandlePainter({
    required this.candles,
    required this.start,
    required this.end,
    required this.decimals,
    required this.levels,
    required this.cross,
    required this.palette,
    required this.labelStyle,
  });

  final List<Candle> candles;
  final int start;
  final int end;
  final int decimals;
  final List<ChartLevel> levels;
  final int? cross;
  final ZxPalette palette;
  final TextStyle labelStyle;

  static const _gridLines = 4;
  static const _bodyFraction = 0.7;
  static const _paddingFraction = 0.06;

  @override
  void paint(Canvas canvas, Size size) {
    if (end <= start) return;
    final plot = Rect.fromLTWH(0, 0, size.width - ZxSize.chartAxisWidth, size.height);
    final slice = candles.sublist(start, end);
    var lo = slice.map((c) => c.l).reduce(math.min);
    var hi = slice.map((c) => c.h).reduce(math.max);
    for (final l in levels) {
      lo = math.min(lo, l.price);
      hi = math.max(hi, l.price);
    }
    final pad = (hi - lo == 0 ? hi.abs() * 0.001 + 1e-9 : hi - lo) * _paddingFraction;
    lo -= pad;
    hi += pad;
    double y(double price) => plot.bottom - (price - lo) / (hi - lo) * plot.height;
    final step = plot.width / slice.length;

    final grid = Paint()
      ..color = palette.chartGrid
      ..strokeWidth = ZxSize.hairline;
    for (var i = 0; i <= _gridLines; i++) {
      final gy = plot.top + plot.height * i / _gridLines;
      canvas.drawLine(Offset(plot.left, gy), Offset(plot.right, gy), grid);
      _label(
        canvas,
        Fmt.price(hi - (hi - lo) * i / _gridLines, decimals: decimals),
        Offset(plot.right + ZxSpace.xs, gy),
        palette.textMuted,
      );
    }

    final wick = Paint()..strokeWidth = ZxSize.hairline;
    final body = Paint();
    for (var i = 0; i < slice.length; i++) {
      final c = slice[i];
      final up = c.c >= c.o;
      final color = up ? palette.bullish : palette.bearish;
      final cx = plot.left + step * (i + 0.5);
      wick.color = color;
      canvas.drawLine(Offset(cx, y(c.h)), Offset(cx, y(c.l)), wick);
      final top = y(math.max(c.o, c.c));
      final bottom = y(math.min(c.o, c.c));
      body.color = color;
      canvas.drawRect(
        Rect.fromLTRB(cx - step * _bodyFraction / 2, top, cx + step * _bodyFraction / 2, math.max(bottom, top + 1)),
        body,
      );
    }

    for (final l in levels) {
      _dashed(canvas, y(l.price), plot, l.color);
      _tag(canvas, '${l.label} ${Fmt.price(l.price, decimals: decimals)}', y(l.price), plot, l.color);
    }

    final last = candles[end - 1].c;
    final lastColor = last >= candles[end - 1].o ? palette.bullish : palette.bearish;
    _dashed(canvas, y(last), plot, lastColor);
    _tag(canvas, Fmt.price(last, decimals: decimals), y(last), plot, lastColor, axis: true);

    final x = cross;
    if (x != null && x >= start && x < end) {
      final cx = plot.left + step * (x - start + 0.5);
      final hair = Paint()
        ..color = palette.chartCrosshair
        ..strokeWidth = ZxSize.hairline;
      canvas.drawLine(Offset(cx, plot.top), Offset(cx, plot.bottom), hair);
      final cy = y(candles[x].c);
      canvas.drawLine(Offset(plot.left, cy), Offset(plot.right, cy), hair);
    }
  }

  void _dashed(Canvas canvas, double y, Rect plot, Color color) {
    final paint = Paint()
      ..color = color.withValues(alpha: 0.7)
      ..strokeWidth = ZxSize.hairline;
    const dash = ZxSpace.xs;
    for (var x = plot.left; x < plot.right; x += dash * 2) {
      canvas.drawLine(Offset(x, y), Offset(math.min(x + dash, plot.right), y), paint);
    }
  }

  void _tag(Canvas canvas, String text, double y, Rect plot, Color color, {bool axis = false}) {
    final tp = TextPainter(
      text: TextSpan(
        text: text,
        style: labelStyle.copyWith(color: palette.textOnAccent),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    final left = axis ? plot.right + ZxSpace.xxs : plot.right - tp.width - ZxSpace.md;
    final rect = Rect.fromLTWH(left, y - tp.height / 2 - ZxSpace.xxs, tp.width + ZxSpace.sm, tp.height + ZxSpace.xs);
    canvas.drawRRect(RRect.fromRectAndRadius(rect, const Radius.circular(ZxRadius.sm / 2)), Paint()..color = color);
    tp.paint(canvas, Offset(rect.left + ZxSpace.xs, rect.top + ZxSpace.xxs));
  }

  void _label(Canvas canvas, String text, Offset at, Color color) {
    final tp = TextPainter(
      text: TextSpan(
        text: text,
        style: labelStyle.copyWith(color: color),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    tp.paint(canvas, Offset(at.dx, at.dy - tp.height / 2));
  }

  @override
  bool shouldRepaint(_CandlePainter old) =>
      old.candles != candles ||
      old.start != start ||
      old.end != end ||
      old.cross != cross ||
      old.levels != levels ||
      old.palette != palette;
}

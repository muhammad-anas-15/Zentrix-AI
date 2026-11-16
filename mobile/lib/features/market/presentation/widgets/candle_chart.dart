import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:intl/intl.dart' show DateFormat;

import '../../../../core/format/formatters.dart';
import '../../../../core/l10n.dart';
import '../../../../core/theme/theme.dart';
import '../../../../core/theme/tokens.dart';
import '../../../../core/widgets/motion.dart';
import '../../domain/models.dart';

/// A horizontal price line drawn over the chart (entry, stop, targets).
@immutable
class ChartLevel {
  const ChartLevel({required this.price, required this.label, required this.color});

  final double price;
  final String label;
  final Color color;
}

/// A shaded price band (e.g. entry to stop, entry to target).
@immutable
class ChartZone {
  const ChartZone({required this.from, required this.to, required this.color});

  final double from;
  final double to;
  final Color color;
}

/// One ghost candle of a projection (prices of a projected path, never traded prices).
@immutable
class ProjectedCandle {
  const ProjectedCandle({
    required this.o,
    required this.h,
    required this.l,
    required this.c,
    required this.bandLow,
    required this.bandHigh,
  });

  final double o;
  final double h;
  final double l;
  final double c;
  final double bandLow;
  final double bandHigh;
}

/// A projected path drawn to the right of the candle it starts from ([anchor], the open time of the last closed
/// candle): ghost candles and a shaded band. Steps that fall on candles already on the chart (the forming one)
/// show only the band.
@immutable
class ChartProjection {
  const ChartProjection({required this.anchor, required this.steps, required this.color, required this.label});

  final DateTime anchor;
  final List<ProjectedCandle> steps;
  final Color color;
  final String label;
}

/// Candles to mark (a detected pattern), from [from] (open time of its first candle) to [to].
@immutable
class ChartHighlight {
  const ChartHighlight({required this.from, required this.to, required this.label, required this.color});

  final DateTime from;
  final DateTime to;
  final String label;
  final Color color;
}

/// What the chart knows about the live feed: whether ticks are real time, when the current candle closes, and
/// how far the device clock is from the server's (for the countdown).
@immutable
class ChartLive {
  const ChartLive({required this.live, required this.closesAt, this.clockOffset = Duration.zero});

  factory ChartLive.from(LiveCandle c) =>
      ChartLive(live: c.live, closesAt: c.closesAt, clockOffset: c.serverTime.difference(DateTime.now()));

  final bool live;
  final DateTime? closesAt;
  final Duration clockOffset; // server - device
}

/// Interactive candlestick chart in the style of a trading terminal: drag to pan, pinch to zoom, long-press
/// (or hover with a mouse) for the crosshair; "jump to latest" resets the view. The forming candle eases to each
/// tick; the price line carries the countdown to the candle close. An optional projection is drawn as ghost candles
/// to the right. Charts read left to right in every locale.
class CandleChart extends StatefulWidget {
  const CandleChart({
    super.key,
    required this.candles,
    this.decimals,
    this.levels = const [],
    this.zones = const [],
    this.live,
    this.timeframe = '15m',
    this.height = ZxSize.chartHeight,
    this.projection,
    this.highlight,
  });

  final List<Candle> candles;
  final int? decimals;
  final List<ChartLevel> levels;
  final List<ChartZone> zones;
  final ChartLive? live;
  final String timeframe;
  final double height;
  final ChartProjection? projection;
  final ChartHighlight? highlight;

  static const int minVisible = 20;
  static const int initialVisible = 70;

  /// While a projection is shown, at most this many candles fit, so the ghost candles stay readable.
  static const int projectionVisible = 40;

  @override
  State<CandleChart> createState() => _CandleChartState();
}

class _CandleChartState extends State<CandleChart> with SingleTickerProviderStateMixin {
  int _visible = CandleChart.initialVisible;
  double _offset = 0; // candles hidden at the right end (panned back in time)
  int _visibleAtScaleStart = CandleChart.initialVisible;
  Offset? _cross;
  Timer? _clock;

  late final AnimationController _tick = AnimationController(vsync: this, duration: ZxMotion.tick, value: 1);
  Candle? _from; // the last candle as drawn when the newest tick arrived

  int get _count => widget.candles.length;

  int _clampVisible(int v) => v.clamp(math.min(CandleChart.minVisible, _count), math.max(_count, 1));

  @override
  void initState() {
    super.initState();
    _syncClock();
  }

  @override
  void didUpdateWidget(CandleChart old) {
    super.didUpdateWidget(old);
    _syncClock();
    final a = old.candles.isEmpty ? null : old.candles.last;
    final b = widget.candles.isEmpty ? null : widget.candles.last;
    if (a == null || b == null || a == b) return;
    final appended = widget.candles.length - old.candles.length;
    if (b.t == a.t) {
      _from = _shown(old.candles); // ease from what is on screen now to the new tick
    } else if (b.t.isAfter(a.t)) {
      _from = Candle(t: b.t, o: b.o, h: b.o, l: b.o, c: b.o); // a new candle grows out of its open
      if (_offset > 0 && appended > 0) _offset += appended; // keep a panned view where it was
    } else {
      _from = null;
    }
    if (reduceMotion(context)) {
      _tick.value = 1;
    } else {
      _tick.forward(from: 0);
    }
  }

  /// The countdown repaints once a second, only while there is a close to count down to.
  void _syncClock() {
    final wanted = widget.live?.closesAt != null;
    if (wanted && _clock == null) {
      _clock = Timer.periodic(const Duration(seconds: 1), (_) {
        if (mounted) setState(() {});
      });
    } else if (!wanted) {
      _clock?.cancel();
      _clock = null;
    }
  }

  @override
  void dispose() {
    _clock?.cancel();
    _tick.dispose();
    super.dispose();
  }

  /// Last candle as currently drawn (between the previous and the newest tick).
  Candle _shown(List<Candle> candles) {
    final to = candles.last;
    final from = _from;
    if (from == null || from.t != to.t || _tick.value >= 1) return to;
    final t = ZxMotion.emphasized.transform(_tick.value);
    double lerp(double a, double b) => a + (b - a) * t;
    final c = lerp(from.c, to.c);
    return to.copyWith(c: c, h: math.max(lerp(from.h, to.h), c), l: math.min(lerp(from.l, to.l), c));
  }

  ({int start, int end}) _window() {
    final wanted = widget.projection == null ? _visible : math.min(_visible, CandleChart.projectionVisible);
    final visible = _clampVisible(wanted);
    final end = (_count - _offset.round()).clamp(visible, _count);
    return (start: math.max(0, end - visible), end: end);
  }

  String? _countdown() {
    final live = widget.live;
    final closes = live?.closesAt;
    if (live == null || closes == null) return null;
    final left = closes.difference(DateTime.now().add(live.clockOffset)).inSeconds;
    return left > 0 ? Fmt.clock(left) : null;
  }

  int? _crossIndex(({int start, int end}) w, double plotWidth, int slots) {
    final x = _cross?.dx;
    if (x == null || plotWidth <= 0 || w.end <= w.start || x > plotWidth) return null;
    final step = plotWidth / slots;
    final i = w.start + (x / step).floor();
    return i >= w.end ? null : i.clamp(w.start, w.end - 1); // over the projection: no candle readout
  }

  /// Index of the candle a projection starts from (searched from the newest), or null.
  int? _anchorIndex() {
    final p = widget.projection;
    if (p == null) return null;
    for (var i = _count - 1; i >= 0 && i >= _count - 6; i--) {
      if (widget.candles[i].t == p.anchor) return i;
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final zx = context.zx;
    if (_count == 0) {
      return SizedBox(
        height: widget.height,
        child: Center(child: Text(context.l10n.noDataForTimeframe, style: zx.text.secondary)),
      );
    }
    final decimals = widget.decimals ?? Fmt.guessDecimals(widget.candles.last.c);
    // axis labels: dates from 4h up, weekday + time on 1h (labels would otherwise repeat one hour), time below
    final daily = const {'4h', '1d', '1w'}.contains(widget.timeframe);
    final axisFormat = DateFormat(daily ? 'd MMM' : (widget.timeframe == '1h' ? 'E HH:mm' : 'HH:mm'));
    final crossFormat = DateFormat(const {'1d', '1w'}.contains(widget.timeframe) ? 'd MMM yyyy' : 'd MMM HH:mm');
    return Directionality(
      textDirection: TextDirection.ltr,
      child: LayoutBuilder(
        builder: (context, constraints) {
          final w = _window();
          final plotWidth = constraints.maxWidth - ZxSize.chartAxisWidth;
          final anchor = _anchorIndex();
          // room for the projected candles to the right of the newest one, while the view is at the live edge
          final extra = anchor == null || w.end != _count
              ? 0
              : math.max(0, anchor + widget.projection!.steps.length - (_count - 1));
          final slots = math.max(1, w.end - w.start + extra);
          final step = plotWidth / slots;
          final crossIndex = _crossIndex(w, plotWidth, slots);
          var highlightFrom = -1;
          final hl = widget.highlight;
          if (hl != null) {
            for (var i = _count - 1; i >= 0 && i >= _count - 8; i--) {
              if (widget.candles[i].t == hl.from) highlightFrom = i;
            }
          }
          var highlightTo = -1;
          if (hl != null && highlightFrom >= 0) {
            for (var i = highlightFrom; i < _count; i++) {
              if (!widget.candles[i].t.isAfter(hl.to)) highlightTo = i;
            }
          }
          return SizedBox(
            height: widget.height,
            child: MouseRegion(
              onHover: (e) => setState(() => _cross = e.localPosition),
              onExit: (_) => setState(() => _cross = null),
              child: GestureDetector(
                onScaleStart: (_) => _visibleAtScaleStart = _clampVisible(_visible),
                onScaleUpdate: (d) => setState(() {
                  if (d.pointerCount > 1) {
                    _visible = _clampVisible((_visibleAtScaleStart / d.scale).round());
                  } else {
                    _cross = null;
                    _offset = (_offset + d.focalPointDelta.dx / step)
                        .clamp(0, math.max(0, _count - _clampVisible(_visible)))
                        .toDouble();
                  }
                }),
                onLongPressStart: (d) => setState(() => _cross = d.localPosition),
                onLongPressMoveUpdate: (d) => setState(() => _cross = d.localPosition),
                onLongPressEnd: (_) => setState(() => _cross = null),
                child: Stack(
                  children: [
                    Positioned.fill(
                      child: AnimatedBuilder(
                        animation: _tick,
                        builder: (context, _) => CustomPaint(
                          painter: _CandlePainter(
                            candles: widget.candles,
                            last: _shown(widget.candles),
                            start: w.start,
                            end: w.end,
                            slots: slots,
                            projection: anchor == null ? null : widget.projection,
                            anchor: anchor,
                            highlight: highlightFrom >= 0 && highlightTo >= highlightFrom ? hl : null,
                            highlightRange: (highlightFrom, highlightTo),
                            decimals: decimals,
                            levels: widget.levels,
                            zones: widget.zones,
                            cross: _cross,
                            live: widget.live?.live ?? false,
                            countdown: _countdown(),
                            timeLabel: (t) => axisFormat.format(t.toLocal()),
                            crossTimeLabel: (t) => crossFormat.format(t.toLocal()),
                            palette: zx.palette,
                            labelStyle: zx.text.chartLabel,
                          ),
                        ),
                      ),
                    ),
                    if (crossIndex != null)
                      Positioned(
                        top: ZxSpace.xs,
                        left: ZxSpace.xs,
                        right: ZxSize.chartAxisWidth,
                        child: _Readout(
                          candle: crossIndex == _count - 1 ? _shown(widget.candles) : widget.candles[crossIndex],
                          previous: crossIndex > 0 ? widget.candles[crossIndex - 1] : null,
                          decimals: decimals,
                        ),
                      ),
                    if (_offset >= 1)
                      Positioned(
                        right: ZxSize.chartAxisWidth + ZxSpace.sm,
                        bottom: ZxSize.chartTimeAxisHeight + ZxSpace.sm,
                        child: _JumpToLatest(
                          onTap: () => setState(() {
                            _offset = 0;
                            _visible = CandleChart.initialVisible;
                          }),
                        ),
                      ),
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}

class _JumpToLatest extends StatelessWidget {
  const _JumpToLatest({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final p = context.zx.palette;
    return Tooltip(
      message: context.l10n.jumpToLatest,
      child: Material(
        color: p.surfaceRaised,
        shape: CircleBorder(
          side: BorderSide(color: p.glassBorder, width: ZxSize.hairline),
        ),
        child: InkWell(
          customBorder: const CircleBorder(),
          onTap: onTap,
          child: SizedBox.square(
            dimension: ZxSize.chartButton,
            child: Icon(Icons.keyboard_double_arrow_right_rounded, size: ZxSize.iconSm, color: p.textPrimary),
          ),
        ),
      ),
    );
  }
}

/// OHLC, change and volume of the candle under the crosshair.
class _Readout extends StatelessWidget {
  const _Readout({required this.candle, required this.previous, required this.decimals});

  final Candle candle;
  final Candle? previous;
  final int decimals;

  @override
  Widget build(BuildContext context) {
    final zx = context.zx;
    final p = zx.palette;
    String f(double v) => Fmt.price(v, decimals: decimals);
    final ref = previous?.c ?? candle.o;
    final change = ref == 0 ? null : (candle.c / ref - 1) * 100;
    final color = candle.c >= candle.o ? p.bullish : p.bearish;
    final style = zx.text.chartLabel;
    TextSpan part(String k, String v) => TextSpan(
      children: [
        if (k.isNotEmpty)
          TextSpan(
            text: '$k ',
            style: style.copyWith(color: p.textMuted),
          ),
        TextSpan(
          text: '$v  ',
          style: style.copyWith(color: color),
        ),
      ],
    );
    final v = candle.v;
    return Align(
      alignment: Alignment.topLeft,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: p.surfaceRaised.withValues(alpha: 0.92),
          borderRadius: BorderRadius.circular(ZxRadius.sm),
          border: Border.all(color: p.glassBorder, width: ZxSize.hairline),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: ZxSpace.sm, vertical: ZxSpace.xs),
          child: Text.rich(
            TextSpan(
              children: [
                part('O', f(candle.o)),
                part('H', f(candle.h)),
                part('L', f(candle.l)),
                part('C', f(candle.c)),
                if (change != null) part('', Fmt.signedPercent(change)),
                if (v != null) part('V', Fmt.number(v, decimals: v >= 100 ? 0 : 2)),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _CandlePainter extends CustomPainter {
  _CandlePainter({
    required this.candles,
    required this.last,
    required this.start,
    required this.end,
    required this.slots,
    required this.projection,
    required this.anchor,
    required this.highlight,
    required this.highlightRange,
    required this.decimals,
    required this.levels,
    required this.zones,
    required this.cross,
    required this.live,
    required this.countdown,
    required this.timeLabel,
    required this.crossTimeLabel,
    required this.palette,
    required this.labelStyle,
  });

  final List<Candle> candles;
  final Candle last; // the newest candle as currently drawn (eased between ticks)
  final int start;
  final int end;
  final int slots; // candle slots across the plot: the visible candles plus room for a projection
  final ChartProjection? projection;
  final int? anchor; // index of the candle the projection starts from
  final ChartHighlight? highlight;
  final (int, int) highlightRange;
  final int decimals;
  final List<ChartLevel> levels;
  final List<ChartZone> zones;
  final Offset? cross;
  final bool live;
  final String? countdown;
  final String Function(DateTime) timeLabel;
  final String Function(DateTime) crossTimeLabel;
  final ZxPalette palette;
  final TextStyle labelStyle;

  static const _gridLines = 4;
  static const _timeLabels = 4;
  static const _bodyFraction = 0.68;
  static const _paddingFraction = 0.08;

  Candle _at(int i) => i == candles.length - 1 ? last : candles[i];

  @override
  void paint(Canvas canvas, Size size) {
    if (end <= start) return;
    final plot = Rect.fromLTWH(0, 0, size.width - ZxSize.chartAxisWidth, size.height - ZxSize.chartTimeAxisHeight);
    final n = end - start;
    var lo = double.infinity;
    var hi = -double.infinity;
    var maxVol = 0.0;
    for (var i = start; i < end; i++) {
      final c = _at(i);
      lo = math.min(lo, c.l);
      hi = math.max(hi, c.h);
      maxVol = math.max(maxVol, c.v ?? 0);
    }
    for (final l in levels) {
      lo = math.min(lo, l.price);
      hi = math.max(hi, l.price);
    }
    for (final z in zones) {
      lo = math.min(lo, math.min(z.from, z.to));
      hi = math.max(hi, math.max(z.from, z.to));
    }
    final proj = projection;
    final a = anchor;
    if (proj != null && a != null) {
      for (final s in proj.steps) {
        lo = math.min(lo, math.min(s.l, s.bandLow));
        hi = math.max(hi, math.max(s.h, s.bandHigh));
      }
    }
    // keep the candles clear of the volume histogram at the bottom
    final volumeH = maxVol > 0 ? plot.height * ZxEffects.volumeFraction : 0.0;
    final span = hi - lo == 0 ? hi.abs() * 0.001 + 1e-9 : hi - lo;
    hi += span * _paddingFraction;
    lo -= span * _paddingFraction + span * (volumeH / math.max(1, plot.height - volumeH));
    double y(double price) => plot.bottom - (price - lo) / (hi - lo) * plot.height;
    final step = plot.width / slots;
    double cx(int i) => plot.left + step * (i - start + 0.5);

    _grid(canvas, plot, lo, hi, n, cx);

    final hl = highlight;
    final (hlFrom, hlTo) = highlightRange;
    if (hl != null && hlTo >= start) {
      final left = cx(math.max(hlFrom, start)) - step / 2;
      final right = cx(hlTo) + step / 2;
      canvas.drawRRect(
        RRect.fromRectAndRadius(Rect.fromLTRB(left, plot.top, right, plot.bottom), const Radius.circular(ZxRadius.sm)),
        Paint()..color = hl.color.withValues(alpha: ZxEffects.zoneAlpha),
      );
      final tp = _painter(hl.label, hl.color);
      tp.paint(canvas, Offset((right - tp.width).clamp(0.0, math.max(0.0, plot.right - tp.width)), plot.top + 2));
    }

    for (final z in zones) {
      canvas.drawRect(
        Rect.fromLTRB(plot.left, y(math.max(z.from, z.to)), plot.right, y(math.min(z.from, z.to))),
        Paint()..color = z.color.withValues(alpha: ZxEffects.zoneAlpha),
      );
    }

    if (maxVol > 0) {
      for (var i = start; i < end; i++) {
        final c = _at(i);
        final v = c.v;
        if (v == null || v <= 0) continue;
        final h = volumeH * v / maxVol;
        canvas.drawRect(
          Rect.fromLTWH(cx(i) - step * _bodyFraction / 2, plot.bottom - h, step * _bodyFraction, h),
          Paint()..color = (c.c >= c.o ? palette.bullish : palette.bearish).withValues(alpha: ZxEffects.volumeAlpha),
        );
      }
    }

    final wick = Paint()..strokeWidth = (step * 0.08).clamp(ZxSize.hairline, ZxSize.hairline * 2).toDouble();
    final body = Paint();
    final radius = Radius.circular(math.min(step * 0.12, 2));
    for (var i = start; i < end; i++) {
      final c = _at(i);
      final color = c.c >= c.o ? palette.bullish : palette.bearish;
      wick.color = color.withValues(alpha: ZxEffects.candleWickAlpha);
      canvas.drawLine(Offset(cx(i), y(c.h)), Offset(cx(i), y(c.l)), wick);
      final top = y(math.max(c.o, c.c));
      final bottom = math.max(y(math.min(c.o, c.c)), top + 1);
      body.color = color;
      canvas.drawRRect(
        RRect.fromRectAndRadius(
          Rect.fromLTRB(cx(i) - step * _bodyFraction / 2, top, cx(i) + step * _bodyFraction / 2, bottom),
          radius,
        ),
        body,
      );
    }

    for (final l in levels) {
      _dashed(canvas, y(l.price), plot, l.color);
      _tag(canvas, '${l.label} ${Fmt.price(l.price, decimals: decimals)}', y(l.price), plot, l.color);
    }

    if (proj != null && a != null && a >= start) _projection(canvas, plot, proj, a, step, y, cx);

    // price line on the newest visible candle; at the live edge it carries the countdown to the close
    final atEdge = end == candles.length;
    final shownLast = _at(end - 1);
    final lastColor = shownLast.c >= shownLast.o ? palette.bullish : palette.bearish;
    final py = y(shownLast.c);
    _dashed(canvas, py, plot, lastColor);
    if (live && atEdge) {
      final dot = Offset(cx(end - 1), py);
      canvas
        ..drawCircle(
          dot,
          ZxSize.chartLiveDot * 2.5,
          Paint()
            ..color = lastColor.withValues(alpha: 0.30)
            ..maskFilter = const MaskFilter.blur(BlurStyle.normal, ZxSize.chartLiveDot * 1.5),
        )
        ..drawCircle(dot, ZxSize.chartLiveDot, Paint()..color = lastColor);
    }
    _axisTag(canvas, Fmt.price(shownLast.c, decimals: decimals), atEdge ? countdown : null, py, plot, lastColor);

    // crosshair: follows the finger or mouse, with price and time tags on the axes
    final c = cross;
    if (c != null && c.dx <= plot.right && c.dy <= plot.bottom && start + (c.dx / step).floor() < end) {
      final i = (start + (c.dx / step).floor()).clamp(start, end - 1);
      final hair = Paint()
        ..color = palette.chartCrosshair
        ..strokeWidth = ZxSize.hairline;
      _dashedV(canvas, cx(i), plot, hair);
      _dashedH(canvas, c.dy, plot, hair);
      final price = hi - (c.dy - plot.top) / plot.height * (hi - lo);
      _axisTag(
        canvas,
        Fmt.price(price, decimals: decimals),
        null,
        c.dy,
        plot,
        palette.surfaceRaised,
        ink: palette.textPrimary,
        border: palette.chartCrosshair,
      );
      _timeTag(canvas, crossTimeLabel(_at(i).t), cx(i), plot, size);
    }
  }

  /// The projected path: a band from the anchor close through each step's 20-80% range, a dashed median line,
  /// and ghost candles (outlined, translucent) where no real candle exists yet.
  void _projection(
    Canvas canvas,
    Rect plot,
    ChartProjection proj,
    int a,
    double step,
    double Function(double) y,
    double Function(int) cx,
  ) {
    final color = proj.color;
    final start0 = Offset(cx(a), y(candles[a].c));
    final upper = Path()..moveTo(start0.dx, start0.dy);
    final lower = <Offset>[];
    for (var k = 0; k < proj.steps.length; k++) {
      final s = proj.steps[k];
      upper.lineTo(cx(a + k + 1), y(s.bandHigh));
      lower.add(Offset(cx(a + k + 1), y(s.bandLow)));
    }
    for (final pt in lower.reversed) {
      upper.lineTo(pt.dx, pt.dy);
    }
    upper.close();
    canvas
      ..save()
      ..clipRect(plot)
      ..drawPath(upper, Paint()..color = color.withValues(alpha: ZxEffects.zoneAlpha));
    final mid = Paint()
      ..color = color.withValues(alpha: 0.8)
      ..strokeWidth = ZxSize.hairline * 1.5;
    var prev = start0;
    for (var k = 0; k < proj.steps.length; k++) {
      final next = Offset(cx(a + k + 1), y(proj.steps[k].c));
      final d = (next - prev).distance;
      if (d > 0) {
        final dir = (next - prev) / d;
        for (var t = 0.0; t < d; t += ZxSpace.sm) {
          canvas.drawLine(prev + dir * t, prev + dir * math.min(t + ZxSpace.xs, d), mid);
        }
      }
      prev = next;
    }
    // the boundary between candles that happened and the projection
    final firstGhost = math.max(a + 1, candles.length);
    final boundary = cx(firstGhost) - step / 2;
    if (firstGhost - a - 1 < proj.steps.length) {
      _dashedV(
        canvas,
        boundary,
        plot,
        Paint()
          ..color = color.withValues(alpha: 0.5)
          ..strokeWidth = ZxSize.hairline,
      );
      final tp = _painter(proj.label, color);
      // below the pattern label (drawn at the top)
      tp.paint(canvas, Offset(math.min(boundary + ZxSpace.xs, plot.right - tp.width), plot.top + ZxSpace.xl));
    }
    final ghostFill = Paint()..color = color.withValues(alpha: 0.16);
    final ghostLine = Paint()
      ..color = color.withValues(alpha: 0.75)
      ..style = PaintingStyle.stroke
      ..strokeWidth = ZxSize.hairline;
    for (var k = 0; k < proj.steps.length; k++) {
      final i = a + k + 1;
      if (i < candles.length) continue; // a real candle is already there (the forming one)
      final s = proj.steps[k];
      final x = cx(i);
      canvas.drawLine(Offset(x, y(s.h)), Offset(x, y(s.l)), ghostLine);
      final top = y(math.max(s.o, s.c));
      final rect = Rect.fromLTRB(
        x - step * _bodyFraction / 2,
        top,
        x + step * _bodyFraction / 2,
        math.max(y(math.min(s.o, s.c)), top + 1),
      );
      final rr = RRect.fromRectAndRadius(rect, Radius.circular(math.min(step * 0.12, 2)));
      canvas
        ..drawRRect(rr, ghostFill)
        ..drawRRect(rr, ghostLine);
    }
    canvas.restore();
  }

  void _grid(Canvas canvas, Rect plot, double lo, double hi, int n, double Function(int) cx) {
    final grid = Paint()
      ..color = palette.chartGrid
      ..strokeWidth = ZxSize.hairline;
    for (var i = 0; i <= _gridLines; i++) {
      final gy = plot.top + plot.height * i / _gridLines;
      canvas.drawLine(Offset(plot.left, gy), Offset(plot.right, gy), grid);
      if (i == 0 || i == _gridLines) continue;
      final tp = _painter(Fmt.price(hi - (hi - lo) * i / _gridLines, decimals: decimals), palette.textMuted);
      tp.paint(canvas, Offset(plot.right + ZxSpace.sm, gy - tp.height / 2));
    }
    final every = math.max(1, (n / _timeLabels).round());
    for (var i = start + every ~/ 2; i < end; i += every) {
      final x = cx(i);
      canvas.drawLine(Offset(x, plot.top), Offset(x, plot.bottom), grid);
      final tp = _painter(timeLabel(_at(i).t), palette.textMuted);
      final left = (x - tp.width / 2).clamp(0.0, math.max(0.0, plot.right - tp.width)).toDouble();
      tp.paint(canvas, Offset(left, plot.bottom + (ZxSize.chartTimeAxisHeight - tp.height) / 2));
    }
  }

  TextPainter _painter(String text, Color color) => TextPainter(
    text: TextSpan(
      text: text,
      style: labelStyle.copyWith(color: color),
    ),
    textDirection: TextDirection.ltr,
  )..layout();

  void _dashed(Canvas canvas, double y, Rect plot, Color color) => _dashedH(
    canvas,
    y,
    plot,
    Paint()
      ..color = color.withValues(alpha: 0.7)
      ..strokeWidth = ZxSize.hairline,
  );

  void _dashedH(Canvas canvas, double y, Rect plot, Paint paint) {
    const dash = ZxSpace.xs;
    for (var x = plot.left; x < plot.right; x += dash * 2) {
      canvas.drawLine(Offset(x, y), Offset(math.min(x + dash, plot.right), y), paint);
    }
  }

  void _dashedV(Canvas canvas, double x, Rect plot, Paint paint) {
    const dash = ZxSpace.xs;
    for (var y = plot.top; y < plot.bottom; y += dash * 2) {
      canvas.drawLine(Offset(x, y), Offset(x, math.min(y + dash, plot.bottom)), paint);
    }
  }

  /// Label of a level line, inside the plot at the right.
  void _tag(Canvas canvas, String text, double y, Rect plot, Color color) {
    final tp = _painter(text, palette.textOnAccent);
    final rect = Rect.fromLTWH(
      plot.right - tp.width - ZxSpace.md,
      y - tp.height / 2 - ZxSpace.xxs,
      tp.width + ZxSpace.sm,
      tp.height + ZxSpace.xs,
    );
    canvas.drawRRect(RRect.fromRectAndRadius(rect, const Radius.circular(ZxRadius.sm / 2)), Paint()..color = color);
    tp.paint(canvas, Offset(rect.left + ZxSpace.xs, rect.top + ZxSpace.xxs));
  }

  /// Price tag on the right axis, with an optional second line (the countdown to the candle close).
  void _axisTag(
    Canvas canvas,
    String price,
    String? sub,
    double y,
    Rect plot,
    Color fill, {
    Color? ink,
    Color? border,
  }) {
    final color = ink ?? palette.textOnAccent;
    final tp = _painter(price, color);
    final sp = sub == null ? null : _painter(sub, color.withValues(alpha: 0.85));
    final rect = Rect.fromLTWH(
      plot.right + ZxSpace.xxs,
      y - tp.height / 2 - ZxSpace.xxs,
      ZxSize.chartAxisWidth - ZxSpace.xs,
      tp.height + (sp?.height ?? 0) + ZxSpace.xs,
    );
    final rr = RRect.fromRectAndRadius(rect, const Radius.circular(ZxRadius.sm / 2));
    canvas.drawRRect(rr, Paint()..color = fill);
    if (border != null) {
      canvas.drawRRect(
        rr,
        Paint()
          ..color = border
          ..style = PaintingStyle.stroke
          ..strokeWidth = ZxSize.hairline,
      );
    }
    tp.paint(canvas, Offset(rect.left + ZxSpace.xs, rect.top + ZxSpace.xxs));
    sp?.paint(canvas, Offset(rect.left + ZxSpace.xs, rect.top + ZxSpace.xxs + tp.height));
  }

  void _timeTag(Canvas canvas, String text, double x, Rect plot, Size size) {
    final tp = _painter(text, palette.textPrimary);
    final w = tp.width + ZxSpace.sm;
    final left = (x - w / 2).clamp(0.0, math.max(0.0, size.width - w)).toDouble();
    final rect = Rect.fromLTWH(left, plot.bottom + ZxSpace.xxs, w, ZxSize.chartTimeAxisHeight - ZxSpace.xs);
    final rr = RRect.fromRectAndRadius(rect, const Radius.circular(ZxRadius.sm / 2));
    canvas
      ..drawRRect(rr, Paint()..color = palette.surfaceRaised)
      ..drawRRect(
        rr,
        Paint()
          ..color = palette.chartCrosshair
          ..style = PaintingStyle.stroke
          ..strokeWidth = ZxSize.hairline,
      );
    tp.paint(canvas, Offset(rect.left + ZxSpace.xs, rect.top + (rect.height - tp.height) / 2));
  }

  @override
  bool shouldRepaint(_CandlePainter old) =>
      old.candles != candles ||
      old.last != last ||
      old.start != start ||
      old.end != end ||
      old.cross != cross ||
      old.levels != levels ||
      old.zones != zones ||
      old.countdown != countdown ||
      old.live != live ||
      old.slots != slots ||
      old.projection != projection ||
      old.highlight != highlight ||
      old.palette != palette;
}

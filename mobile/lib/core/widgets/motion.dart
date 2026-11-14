import 'package:flutter/material.dart';

import '../theme/theme.dart';
import '../theme/tokens.dart';
import 'surfaces.dart';

/// True when the system asks for reduced motion: pulses, flashes and shimmer are skipped.
bool reduceMotion(BuildContext context) => MediaQuery.maybeDisableAnimationsOf(context) ?? false;

/// A glowing status dot that breathes slowly (the market-condition light).
class StatusOrb extends StatefulWidget {
  const StatusOrb({super.key, required this.color, this.size = ZxSize.orb, this.pulse = true});

  final Color color;
  final double size;
  final bool pulse;

  @override
  State<StatusOrb> createState() => _StatusOrbState();
}

class _StatusOrbState extends State<StatusOrb> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: ZxMotion.pulse);

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (widget.pulse && !reduceMotion(context)) {
      if (!_c.isAnimating) _c.repeat(reverse: true);
    } else {
      _c.stop();
    }
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
    animation: _c,
    builder: (context, _) {
      final t = ZxMotion.standard.transform(_c.value);
      return Container(
        width: widget.size,
        height: widget.size,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          gradient: RadialGradient(
            colors: [Color.lerp(widget.color, context.zx.palette.textOnAccent, 0.35)!, widget.color],
          ),
          boxShadow: [
            BoxShadow(
              color: widget.color.withValues(alpha: 0.35 + 0.35 * t),
              blurRadius: ZxEffects.orbGlowBlur * (0.6 + 0.6 * t),
              spreadRadius: ZxSpace.xxs * t,
            ),
          ],
        ),
      );
    },
  );
}

/// Briefly washes its child in green (value went up) or red (down) when [value] changes, like a live quote.
class FlashOnChange extends StatefulWidget {
  const FlashOnChange({super.key, required this.value, required this.child});

  final double? value;
  final Widget child;

  @override
  State<FlashOnChange> createState() => _FlashOnChangeState();
}

class _FlashOnChangeState extends State<FlashOnChange> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: ZxMotion.flash, value: 1);
  bool _up = true;

  @override
  void didUpdateWidget(FlashOnChange old) {
    super.didUpdateWidget(old);
    final a = old.value;
    final b = widget.value;
    if (a != null && b != null && a != b && !reduceMotion(context)) {
      _up = b > a;
      _c.forward(from: 0);
    }
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final p = context.zx.palette;
    return AnimatedBuilder(
      animation: _c,
      builder: (context, child) {
        final strength = 1 - ZxMotion.emphasized.transform(_c.value);
        final color = (_up ? p.bullish : p.bearish).withValues(alpha: 0.28 * strength);
        return DecoratedBox(
          decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(ZxRadius.sm)),
          child: child,
        );
      },
      child: widget.child,
    );
  }
}

/// Placeholder block with a moving sheen while data loads.
class Skeleton extends StatefulWidget {
  const Skeleton({super.key, this.height = ZxSize.skeletonLine, this.width, this.radius = ZxRadius.sm});

  final double height;
  final double? width;
  final double radius;

  @override
  State<Skeleton> createState() => _SkeletonState();
}

class _SkeletonState extends State<Skeleton> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: ZxMotion.shimmer);

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (reduceMotion(context)) {
      _c.stop();
    } else if (!_c.isAnimating) {
      _c.repeat();
    }
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final p = context.zx.palette;
    return AnimatedBuilder(
      animation: _c,
      builder: (context, _) => Container(
        height: widget.height,
        width: widget.width,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(widget.radius),
          gradient: LinearGradient(
            colors: [p.skeleton, p.skeletonShine, p.skeleton],
            stops: const [0.25, 0.5, 0.75],
            transform: _Slide(_c.value),
          ),
        ),
      ),
    );
  }
}

class _Slide extends GradientTransform {
  const _Slide(this.t);

  final double t;

  @override
  Matrix4 transform(Rect bounds, {TextDirection? textDirection}) =>
      Matrix4.translationValues(bounds.width * (t * 2 - 1), 0, 0);
}

/// A card-shaped loading placeholder.
class SkeletonCard extends StatelessWidget {
  const SkeletonCard({super.key, this.lines = 3});

  final int lines;

  @override
  Widget build(BuildContext context) => GlassCard(
    level: ZxLevel.base,
    child: LayoutBuilder(
      builder: (context, c) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (var i = 0; i < lines; i++) ...[
            if (i > 0) const SizedBox(height: ZxSpace.md),
            Skeleton(width: c.maxWidth * (i == 0 ? 0.45 : (i.isEven ? 0.7 : 0.9))),
          ],
        ],
      ),
    ),
  );
}

/// Fades and slides its child in; [index] staggers items of a list.
class FadeSlideIn extends StatelessWidget {
  const FadeSlideIn({super.key, required this.child, this.index = 0});

  final Widget child;
  final int index;

  @override
  Widget build(BuildContext context) {
    if (reduceMotion(context)) return child;
    final delay = ZxMotion.stagger * index;
    final total = ZxMotion.entrance + delay;
    final start = delay.inMilliseconds / total.inMilliseconds;
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: 1),
      duration: total,
      curve: Interval(start, 1, curve: ZxMotion.emphasized),
      builder: (context, v, child) => Opacity(
        opacity: v,
        child: Transform.translate(offset: Offset(0, (1 - v) * ZxMotion.entranceOffset), child: child),
      ),
      child: child,
    );
  }
}

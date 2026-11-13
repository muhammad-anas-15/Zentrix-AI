import 'package:flutter/material.dart';

import '../l10n.dart';
import '../theme/theme.dart';
import '../theme/tokens.dart';
import 'surfaces.dart';

/// Gold "Premium" label. A label only: premium features are not locked in the app.
class PremiumBadge extends StatelessWidget {
  const PremiumBadge({super.key});

  @override
  Widget build(BuildContext context) {
    final p = context.zx.palette;
    return Semantics(
      label: context.l10n.premium,
      child: Pill(
        label: context.l10n.premium,
        color: p.gold,
        background: p.goldSoft,
        icon: Icons.workspace_premium_outlined,
      ),
    );
  }
}

/// Strength tier exactly as the server sends it. "Very Weak - Wait" is neutral grey: no colour suggests action.
class StrengthBadge extends StatelessWidget {
  const StrengthBadge(this.strength, {super.key});

  final String strength;

  @override
  Widget build(BuildContext context) {
    final p = context.zx.palette;
    final (fg, bg) = switch (strength) {
      'Strong' => (p.accent, p.accentSoft),
      'Good' => (p.accentAlt, p.accentSoft),
      'Moderate' || 'Weak' => (p.caution, p.cautionSoft),
      _ => (p.neutral, p.neutralSoft),
    };
    return Pill(label: strengthLabel(context.l10n, strength), color: fg, background: bg);
  }
}

/// Up / down. Without a demonstrated edge the direction is shown in neutral grey.
class DirectionChip extends StatelessWidget {
  const DirectionChip({super.key, required this.up, required this.actionable});

  final bool up;
  final bool actionable;

  @override
  Widget build(BuildContext context) {
    final p = context.zx.palette;
    final l = context.l10n;
    final (fg, bg) = !actionable
        ? (p.neutral, p.neutralSoft)
        : up
        ? (p.bullish, p.bullishSoft)
        : (p.bearish, p.bearishSoft);
    return Pill(
      label: up ? l.directionUp : l.directionDown,
      color: fg,
      background: bg,
      icon: up ? Icons.north_east : Icons.south_east,
    );
  }
}

/// Market-condition light: green / amber / red / unknown, with a soft glow.
class ConditionLight extends StatelessWidget {
  const ConditionLight(this.light, {super.key, this.showLabel = true});

  final String light;
  final bool showLabel;

  static Color colorOf(BuildContext context, String light) {
    final p = context.zx.palette;
    return switch (light) {
      'green' => p.bullish,
      'amber' => p.caution,
      'red' => p.bearish,
      _ => p.neutral,
    };
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final color = colorOf(context, light);
    final label = switch (light) {
      'green' => l.lightGreen,
      'amber' => l.lightAmber,
      'red' => l.lightRed,
      _ => l.lightUnknown,
    };
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: ZxSize.lightDot,
          height: ZxSize.lightDot,
          decoration: BoxDecoration(
            color: color,
            shape: BoxShape.circle,
            boxShadow: [BoxShadow(color: color.withValues(alpha: 0.6), blurRadius: ZxSpace.md)],
          ),
        ),
        if (showLabel) ...[
          const SizedBox(width: ZxSpace.sm),
          Text(label, style: context.zx.text.bodyStrong.copyWith(color: color)),
        ],
      ],
    );
  }
}

/// News guard state chip.
class NewsStateChip extends StatelessWidget {
  const NewsStateChip(this.state, {super.key});

  final String state;

  @override
  Widget build(BuildContext context) {
    final p = context.zx.palette;
    final l = context.l10n;
    final (fg, bg, label) = switch (state) {
      'blackout' => (p.bearish, p.bearishSoft, l.newsStateBlackout),
      'caution' => (p.caution, p.cautionSoft, l.newsStateCaution),
      'clear' => (p.bullish, p.bullishSoft, l.newsStateClear),
      _ => (p.neutral, p.neutralSoft, l.newsStateUnknown),
    };
    return Pill(label: label, color: fg, background: bg, icon: Icons.event_note_outlined);
  }
}

/// Signal outcome chip (null = still pending).
class OutcomeChip extends StatelessWidget {
  const OutcomeChip(this.outcome, {super.key});

  final String? outcome;

  @override
  Widget build(BuildContext context) {
    final p = context.zx.palette;
    final l = context.l10n;
    final (fg, bg, label) = switch (outcome) {
      'win' => (p.bullish, p.bullishSoft, l.outcomeWin),
      'loss' => (p.bearish, p.bearishSoft, l.outcomeLoss),
      'flat' => (p.neutral, p.neutralSoft, l.outcomeFlat),
      'void' => (p.neutral, p.neutralSoft, l.outcomeVoid),
      _ => (p.accentAlt, p.accentSoft, l.outcomePending),
    };
    return Pill(label: label, color: fg, background: bg);
  }
}

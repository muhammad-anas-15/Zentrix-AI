import 'package:flutter/material.dart';

import '../../../../core/format/formatters.dart';
import '../../../../core/l10n.dart';
import '../../../../core/theme/theme.dart';
import '../../../../core/theme/tokens.dart';
import '../../../../core/widgets/badges.dart';
import '../../../../core/widgets/surfaces.dart';
import '../../domain/models.dart';

/// The live signal, presented honestly: the strength tier as earned out of sample ("Very Weak - Wait" is
/// neutral), the calibrated probability, and a plain note when the model has no demonstrated edge.
class SignalCard extends StatelessWidget {
  const SignalCard({super.key, required this.signal, this.onTap});

  final Signal signal;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final zx = context.zx;
    final s = signal;
    final tier = s.backtestTier;
    final tierRate = tier?['rate'] as num?;
    final tierN = (tier?['n'] as num?)?.toInt() ?? 0;
    return GlassCard(
      onTap: onTap,
      accent: s.isActionable ? (s.isUp ? zx.palette.bullish : zx.palette.bearish) : null,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(child: Text('${l.signalTitle} · ${s.symbol} · ${s.timeframe}', style: zx.text.label)),
              if (s.premium != null) const PremiumBadge(),
            ],
          ),
          const SizedBox(height: ZxSpace.md),
          Wrap(
            spacing: ZxSpace.sm,
            runSpacing: ZxSpace.sm,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              DirectionChip(up: s.isUp, actionable: s.isActionable),
              StrengthBadge(s.strength),
              if (s.outcome != null) OutcomeChip(s.outcome!.outcome),
            ],
          ),
          const SizedBox(height: ZxSpace.md),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(Fmt.ratio(s.confidence), style: zx.text.metric),
              const SizedBox(width: ZxSpace.sm),
              Expanded(child: Text('${l.modelProbability} ${l.horizonCandles(s.horizon)}', style: zx.text.caption)),
            ],
          ),
          if (!s.isActionable) ...[
            const SizedBox(height: ZxSpace.md),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(Icons.balance_outlined, size: ZxSize.iconSm, color: zx.palette.neutral),
                const SizedBox(width: ZxSpace.sm),
                Expanded(
                  child: Text(l.noEdgeNote, style: zx.text.caption.copyWith(color: zx.palette.textSecondary)),
                ),
              ],
            ),
          ],
          if (tierRate != null && tierN > 0) ...[
            const SizedBox(height: ZxSpace.sm),
            Text(l.backtestTier(Fmt.ratio(tierRate.toDouble()), tierN), style: zx.text.caption),
          ],
          const SizedBox(height: ZxSpace.md),
          Text(Fmt.dateTime(s.createdAt, context.localeCode), style: zx.text.caption),
          const SizedBox(height: ZxSpace.sm),
          const Disclaimer(),
        ],
      ),
    );
  }
}

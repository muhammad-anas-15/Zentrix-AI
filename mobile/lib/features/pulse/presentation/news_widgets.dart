import 'package:flutter/material.dart';

import '../../../core/format/formatters.dart';
import '../../../core/l10n.dart';
import '../../../core/links.dart';
import '../../../core/theme/theme.dart';
import '../../../core/theme/tokens.dart';
import '../../../core/widgets/surfaces.dart';
import '../domain/models.dart';

/// Opens a headline at its publisher (outside the app).
Future<void> openNews(BuildContext context, String url) => openExternal(context, url);

/// High / Medium / Low. Colours follow the news guard: red, amber, grey.
class ImpactTag extends StatelessWidget {
  const ImpactTag(this.impact, {super.key});

  final String impact;

  @override
  Widget build(BuildContext context) {
    final p = context.zx.palette;
    final l = context.l10n;
    final (fg, bg, label) = switch (impact) {
      'high' => (p.bearish, p.bearishSoft, l.impactHigh),
      'medium' => (p.caution, p.cautionSoft, l.impactMedium),
      _ => (p.neutral, p.neutralSoft, l.impactLow),
    };
    return Pill(label: label, color: fg, background: bg, icon: Icons.bolt_rounded);
  }
}

/// Currency / asset badge (USD, XAU, BTC...). Tapping it filters the Pulse by that asset.
class AssetBadge extends StatelessWidget {
  const AssetBadge(this.asset, {super.key, this.selected = false, this.onTap});

  final String asset;
  final bool selected;
  final VoidCallback? onTap;

  static const _metals = {'XAU', 'XAG'};
  static const _fiat = {'USD', 'EUR', 'GBP', 'JPY', 'CHF', 'AUD', 'NZD', 'CAD', 'CNY', 'INR', 'PKR'};

  @override
  Widget build(BuildContext context) {
    final zx = context.zx;
    final p = zx.palette;
    final color = _metals.contains(asset)
        ? p.gold
        : _fiat.contains(asset)
        ? p.textSecondary
        : asset == 'OIL'
        ? p.caution
        : p.accent;
    final label = asset == 'CRYPTO' ? context.l10n.assetCrypto : asset;
    return Semantics(
      button: onTap != null,
      selected: selected,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(ZxRadius.sm),
        child: AnimatedContainer(
          duration: ZxMotion.fast,
          padding: const EdgeInsets.symmetric(horizontal: ZxSpace.sm, vertical: ZxSpace.xxs),
          decoration: BoxDecoration(
            color: selected ? color.withValues(alpha: 0.22) : p.glass,
            borderRadius: BorderRadius.circular(ZxRadius.sm),
            border: Border.all(
              color: color.withValues(alpha: selected ? 0.8 : 0.35),
              width: ZxSize.hairline,
            ),
          ),
          child: Text(
            label,
            style: zx.text.chartLabel.copyWith(color: color, fontWeight: ZxType.bold),
          ),
        ),
      ),
    );
  }
}

IconData newsKindIcon(String kind) => switch (kind) {
  'central_bank' => Icons.account_balance_outlined,
  'regulator' => Icons.gavel_rounded,
  _ => Icons.article_outlined,
};

/// One headline: impact, source and age, the title, asset badges. Opens the article at its publisher.
class NewsCard extends StatelessWidget {
  const NewsCard({super.key, required this.item, this.selectedAsset, this.onAsset, this.highlight = false});

  final NewsItem item;
  final String? selectedAsset;
  final ValueChanged<String>? onAsset;
  final bool highlight;

  @override
  Widget build(BuildContext context) {
    final zx = context.zx;
    final p = zx.palette;
    final l = context.l10n;
    final age = item.ageS < 60 ? l.justNow : l.agoShort(Fmt.ago(item.ageS));
    return GlassCard(
      level: highlight ? ZxLevel.raised : ZxLevel.base,
      accent: highlight ? p.bearish : null,
      tint: highlight ? p.bearish : null,
      padding: const EdgeInsets.fromLTRB(ZxSpace.lg, ZxSpace.md, ZxSpace.md, ZxSpace.md),
      onTap: () => openNews(context, item.url),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              ImpactTag(item.impact),
              const SizedBox(width: ZxSpace.sm),
              Icon(newsKindIcon(item.kind), size: ZxSize.iconXs, color: p.textMuted),
              const SizedBox(width: ZxSpace.xs),
              Expanded(
                child: Text(
                  '${item.sourceName} · $age',
                  style: zx.text.caption,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              Icon(Icons.open_in_new_rounded, size: ZxSize.iconXs, color: p.textMuted),
            ],
          ),
          const SizedBox(height: ZxSpace.sm),
          Text(item.title, style: zx.text.bodyStrong, maxLines: 3, overflow: TextOverflow.ellipsis),
          if (item.assets.isNotEmpty) ...[
            const SizedBox(height: ZxSpace.sm),
            Wrap(
              spacing: ZxSpace.xs,
              runSpacing: ZxSpace.xs,
              children: [
                for (final a in item.assets.take(6))
                  AssetBadge(a, selected: a == selectedAsset, onTap: onAsset == null ? null : () => onAsset!(a)),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

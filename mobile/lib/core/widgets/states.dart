import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../l10n.dart';
import '../network/api_exception.dart';
import '../theme/theme.dart';
import '../theme/tokens.dart';
import 'badges.dart';
import 'motion.dart';
import 'surfaces.dart';

/// Loading / error / data for an AsyncValue. A `premium_required` error (server enforcing premium) becomes a
/// plain "not on your plan" card with nothing to buy.
class AsyncValueView<T> extends StatelessWidget {
  const AsyncValueView({super.key, required this.value, required this.data, this.onRetry, this.compact = false});

  final AsyncValue<T> value;
  final Widget Function(T data) data;
  final VoidCallback? onRetry;
  final bool compact;

  @override
  Widget build(BuildContext context) => value.when(
    // keep showing the last data while a refresh runs (pull-to-refresh, periodic updates)
    skipLoadingOnReload: true,
    skipLoadingOnRefresh: true,
    data: data,
    loading: () => SkeletonCard(lines: compact ? 2 : 3),
    error: (e, _) {
      if (e is ApiException && e.isPremiumRequired) return PremiumLockedCard(feature: e.premiumFeature);
      return ErrorView(error: e, onRetry: onRetry);
    },
  );
}

class LoadingView extends StatelessWidget {
  const LoadingView({super.key, this.compact = false});

  final bool compact;

  @override
  Widget build(BuildContext context) => Padding(
    padding: EdgeInsets.all(compact ? ZxSpace.md : ZxSpace.xxxl),
    child: const Center(
      child: SizedBox(
        width: ZxSize.iconLg,
        height: ZxSize.iconLg,
        child: CircularProgressIndicator(strokeWidth: ZxSize.progressStroke),
      ),
    ),
  );
}

class ErrorView extends StatelessWidget {
  const ErrorView({super.key, required this.error, this.onRetry});

  final Object error;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final message = switch (error) {
      ApiException(isNetwork: true) => l.errorNetwork,
      ApiException(:final message) => message,
      _ => l.errorGeneric,
    };
    return GlassCard(
      child: Row(
        children: [
          Icon(Icons.error_outline, color: context.zx.palette.bearish),
          const SizedBox(width: ZxSpace.md),
          Expanded(child: Text(message, style: context.zx.text.secondary)),
          if (onRetry != null) TextButton(onPressed: onRetry, child: Text(l.retry)),
        ],
      ),
    );
  }
}

class EmptyView extends StatelessWidget {
  const EmptyView({super.key, required this.message, this.icon = Icons.inbox_outlined});

  final String message;
  final IconData icon;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: ZxSpace.xxl),
    child: Column(
      children: [
        Icon(icon, size: ZxSize.iconXl, color: context.zx.palette.textMuted),
        const SizedBox(height: ZxSpace.md),
        Text(message, style: context.zx.text.secondary, textAlign: TextAlign.center),
      ],
    ),
  );
}

/// Shown only when the server enforces premium and the user lacks the feature. No paywall, nothing to buy.
class PremiumLockedCard extends StatelessWidget {
  const PremiumLockedCard({super.key, this.feature});

  final String? feature;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final name = feature == null ? l.premium : featureTitle(l, feature!);
    return GlassCard(
      accent: context.zx.palette.gold,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(child: Text(l.premiumLockedTitle, style: context.zx.text.bodyStrong)),
              const PremiumBadge(),
            ],
          ),
          const SizedBox(height: ZxSpace.sm),
          Text(l.premiumLockedBody(name), style: context.zx.text.secondary),
        ],
      ),
    );
  }
}

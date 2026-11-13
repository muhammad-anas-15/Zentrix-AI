import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/l10n.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/theme/theme.dart';
import '../../../core/theme/tokens.dart';
import '../../../core/widgets/badges.dart';
import '../../../core/widgets/states.dart';
import '../../../core/widgets/surfaces.dart';
import '../../auth/application/session.dart';
import '../../auth/data/auth_repository.dart';
import '../../auth/domain/models.dart';
import '../../auth/presentation/sign_in_prompt.dart';
import '../application/preferences.dart';

class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  Future<void> _setLanguage(WidgetRef ref, String code) async {
    await ref.read(preferencesProvider.notifier).setLanguage(code);
    if (ref.read(currentUserProvider) == null) return;
    try {
      final user = await ref.read(authRepositoryProvider).updateMe(locale: code);
      ref.read(sessionProvider.notifier).updateUser(user);
    } on ApiException {
      // the device setting already applies; the account copy syncs next time
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final zx = context.zx;
    final prefs = ref.watch(preferencesProvider);
    final user = ref.watch(currentUserProvider);
    final lang = prefs.locale?.languageCode ?? Localizations.localeOf(context).languageCode;

    return ZxPage(
      title: l.settingsTitle,
      children: [
        if (user == null) const SignInPrompt() else _ProfileCard(user: user),
        SectionHeader(l.language),
        SegmentedButton<String>(
          segments: [
            ButtonSegment(value: 'en', label: Text(l.languageEnglish)),
            ButtonSegment(value: 'ur', label: Text(l.languageUrdu)),
          ],
          selected: {lang},
          showSelectedIcon: false,
          onSelectionChanged: (s) => _setLanguage(ref, s.first),
        ),
        SectionHeader(l.theme),
        SegmentedButton<ThemeMode>(
          segments: [
            ButtonSegment(value: ThemeMode.system, label: Text(l.themeSystem)),
            ButtonSegment(value: ThemeMode.dark, label: Text(l.themeDark)),
            ButtonSegment(value: ThemeMode.light, label: Text(l.themeLight)),
          ],
          selected: {prefs.themeMode},
          showSelectedIcon: false,
          onSelectionChanged: (s) => ref.read(preferencesProvider.notifier).setThemeMode(s.first),
        ),
        if (user != null) ...[
          SectionHeader(l.planTitle),
          const _AccessCard(),
          SectionHeader(l.profile),
          GlassCard(
            padding: EdgeInsets.zero,
            child: Column(
              children: [
                ListTile(
                  leading: const Icon(Icons.logout),
                  title: Text(l.signOut),
                  onTap: () => ref.read(sessionProvider.notifier).signOut(),
                ),
                ListTile(
                  leading: const Icon(Icons.devices_other_outlined),
                  title: Text(l.signOutEverywhere),
                  onTap: () => ref.read(sessionProvider.notifier).signOutEverywhere(),
                ),
                ListTile(
                  key: const Key('deleteAccount'),
                  leading: Icon(Icons.delete_forever_outlined, color: zx.palette.bearish),
                  title: Text(l.deleteAccount, style: zx.text.body.copyWith(color: zx.palette.bearish)),
                  onTap: () => context.push('/settings/delete-account'),
                ),
              ],
            ),
          ),
        ],
        SectionHeader(l.about),
        GlassCard(child: Text(l.disclaimerLong, style: zx.text.secondary)),
      ],
    );
  }
}

class _ProfileCard extends StatelessWidget {
  const _ProfileCard({required this.user});

  final AppUser user;

  @override
  Widget build(BuildContext context) {
    final zx = context.zx;
    final l = context.l10n;
    final name = user.displayName ?? user.email ?? '';
    return GlassCard(
      child: Row(
        children: [
          CircleAvatar(
            backgroundColor: zx.palette.accentSoft,
            foregroundColor: zx.palette.textPrimary,
            child: Text(name.isEmpty ? '?' : name.characters.first.toUpperCase()),
          ),
          const SizedBox(width: ZxSpace.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(name, style: zx.text.bodyStrong),
                if (user.email != null) Text(user.email!, style: zx.text.caption),
              ],
            ),
          ),
          Pill(
            label: user.plan == 'premium' ? l.planPremium : l.planFree,
            color: user.plan == 'premium' ? zx.palette.gold : zx.palette.textSecondary,
            background: user.plan == 'premium' ? zx.palette.goldSoft : zx.palette.glassStrong,
          ),
        ],
      ),
    );
  }
}

/// Plan and premium features: labels only. While the server does not enforce premium, everything is open.
class _AccessCard extends ConsumerWidget {
  const _AccessCard();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final zx = context.zx;
    return AsyncValueView<Access?>(
      value: ref.watch(accessProvider),
      compact: true,
      onRetry: () => ref.invalidate(accessProvider),
      data: (a) {
        if (a == null) return const SizedBox.shrink();
        final premium = a.features.where((f) => f.tier == 'premium').toList();
        return GlassCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(child: Text(l.premiumFeatures, style: zx.text.bodyStrong)),
                  const PremiumBadge(),
                ],
              ),
              if (!a.enforced) ...[
                const SizedBox(height: ZxSpace.xs),
                Text(l.premiumOpenBeta, style: zx.text.caption.copyWith(color: zx.palette.gold)),
              ],
              const SizedBox(height: ZxSpace.md),
              for (final f in premium)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: ZxSpace.xs),
                  child: Row(
                    children: [
                      Icon(
                        f.available ? Icons.check_circle_outline : Icons.lock_outline,
                        size: ZxSize.iconSm,
                        color: f.available ? zx.palette.bullish : zx.palette.textMuted,
                      ),
                      const SizedBox(width: ZxSpace.sm),
                      Expanded(child: Text(featureTitle(l, f.key), style: zx.text.body)),
                      Text(f.available ? l.featureAvailable : l.featureLocked, style: zx.text.caption),
                    ],
                  ),
                ),
            ],
          ),
        );
      },
    );
  }
}

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/l10n.dart';
import '../../../core/theme/theme.dart';
import '../../../core/theme/tokens.dart';
import '../../auth/application/session.dart';

/// App-bar entry to Settings and the account: the user's initial (or a person icon for guests).
class ProfileButton extends ConsumerWidget {
  const ProfileButton({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final p = context.zx.palette;
    final user = ref.watch(currentUserProvider);
    final name = user?.displayName ?? user?.email ?? '';
    return Padding(
      padding: const EdgeInsetsDirectional.only(end: ZxSpace.sm),
      child: IconButton(
        key: const Key('profileButton'),
        tooltip: context.l10n.settingsTitle,
        onPressed: () => context.push('/settings'),
        icon: Container(
          width: ZxSize.brandMark,
          height: ZxSize.brandMark,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            gradient: user == null ? null : p.accentGradient,
            color: user == null ? p.glassStrong : null,
            border: Border.all(color: p.glassBorder, width: ZxSize.hairline),
          ),
          child: user == null || name.isEmpty
              ? Icon(Icons.person_outline_rounded, size: ZxSize.iconSm, color: p.textSecondary)
              : Text(name.characters.first.toUpperCase(), style: context.zx.text.label.copyWith(color: p.textOnAccent)),
        ),
      ),
    );
  }
}

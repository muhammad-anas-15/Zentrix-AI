import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/l10n.dart';
import '../../../core/theme/theme.dart';
import '../../../core/theme/tokens.dart';
import '../../../core/widgets/surfaces.dart';
import '../application/session.dart';

/// Guests see this where an account is needed (journal, alerts, settings).
class SignInPrompt extends ConsumerWidget {
  const SignInPrompt({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    return GlassCard(
      accent: context.zx.palette.accent,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Icon(Icons.lock_person_outlined, size: ZxSize.iconXl, color: context.zx.palette.accent),
          const SizedBox(height: ZxSpace.md),
          Text(l.signInRequiredTitle, style: context.zx.text.title, textAlign: TextAlign.center),
          const SizedBox(height: ZxSpace.sm),
          Text(l.signInRequiredBody, style: context.zx.text.secondary, textAlign: TextAlign.center),
          const SizedBox(height: ZxSpace.lg),
          FilledButton(onPressed: ref.read(sessionProvider.notifier).goToSignIn, child: Text(l.signIn)),
        ],
      ),
    );
  }
}

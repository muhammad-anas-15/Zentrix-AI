import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/l10n.dart';
import '../../../core/theme/theme.dart';
import '../../../core/theme/tokens.dart';
import '../../../core/widgets/states.dart';
import '../../../core/widgets/surfaces.dart';
import '../application/session.dart';

/// Shown while a saved session is restored (and when the server is unreachable at start-up).
class SplashScreen extends ConsumerWidget {
  const SplashScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider);
    final l = context.l10n;
    final t = context.zx.text;
    return Scaffold(
      body: ZxBackground(
        child: SafeArea(
          child: Center(
            child: Padding(
              padding: const EdgeInsets.all(ZxSpace.xxl),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(l.appName, style: t.display),
                  const SizedBox(height: ZxSpace.sm),
                  Text(l.tagline, style: t.secondary, textAlign: TextAlign.center),
                  const SizedBox(height: ZxSpace.xxxl),
                  if (session is SessionOffline) ...[
                    Text(l.errorNetwork, style: t.secondary, textAlign: TextAlign.center),
                    const SizedBox(height: ZxSpace.lg),
                    FilledButton(onPressed: () => ref.read(sessionProvider.notifier).restore(), child: Text(l.retry)),
                    TextButton(
                      onPressed: () => ref.read(sessionProvider.notifier).continueAsGuest(),
                      child: Text(l.continueAsGuest),
                    ),
                  ] else
                    const LoadingView(compact: true),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

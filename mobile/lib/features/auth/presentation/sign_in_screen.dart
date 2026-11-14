import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/l10n.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/providers.dart';
import '../../../core/theme/theme.dart';
import '../../../core/theme/tokens.dart';
import '../../../core/widgets/motion.dart';
import '../../../core/widgets/surfaces.dart';
import '../application/session.dart';
import '../data/auth_repository.dart';

class SignInScreen extends ConsumerStatefulWidget {
  const SignInScreen({super.key});

  @override
  ConsumerState<SignInScreen> createState() => _SignInScreenState();
}

class _SignInScreenState extends ConsumerState<SignInScreen> {
  final _email = TextEditingController(text: 'dev@example.com');
  bool _busy = false;

  @override
  void dispose() {
    _email.dispose();
    super.dispose();
  }

  Future<void> _run(Future<void> Function() action) async {
    setState(() => _busy = true);
    try {
      await action();
    } on Object catch (e) {
      if (!mounted) return;
      final l = context.l10n;
      final msg = switch (e) {
        ApiException(isNetwork: true) => l.errorNetwork,
        ApiException(:final message) => message,
        _ => l.errorGeneric,
      };
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final t = context.zx.text;
    final p = context.zx.palette;
    final config = ref.watch(appConfigProvider);
    final google = ref.watch(googleAuthProvider);
    final session = ref.watch(sessionProvider);
    final notifier = ref.read(sessionProvider.notifier);
    final reason = session is SessionSignedOut ? session.reason : SignedOutReason.none;

    return Scaffold(
      body: ZxBackground(
        child: SafeArea(
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: ZxSize.maxContentWidth),
              child: ListView(
                padding: const EdgeInsets.all(ZxSpace.xxl),
                children: [
                  const SizedBox(height: ZxSpace.xxl),
                  const FadeSlideIn(
                    child: Align(
                      alignment: AlignmentDirectional.centerStart,
                      child: BrandMark(size: ZxSize.brandHero),
                    ),
                  ),
                  const SizedBox(height: ZxSpace.xl),
                  FadeSlideIn(
                    index: 1,
                    child: Text(l.appName.toUpperCase(), style: t.overline.copyWith(color: p.accent)),
                  ),
                  const SizedBox(height: ZxSpace.sm),
                  FadeSlideIn(index: 2, child: Text(l.signInTitle, style: t.display)),
                  const SizedBox(height: ZxSpace.md),
                  FadeSlideIn(index: 3, child: Text(l.signInSubtitle, style: t.secondary)),
                  const SizedBox(height: ZxSpace.xxl),
                  if (reason != SignedOutReason.none) ...[
                    GlassCard(
                      accent: reason == SignedOutReason.deleted ? p.bullish : p.caution,
                      child: Text(
                        reason == SignedOutReason.deleted ? l.accountDeleted : l.sessionExpired,
                        style: t.body,
                      ),
                    ),
                    const SizedBox(height: ZxSpace.lg),
                  ],
                  FadeSlideIn(
                    index: 4,
                    child: GlassCard(
                      level: ZxLevel.base,
                      child: Column(
                        children: [
                          _Highlight(icon: Icons.radar_rounded, text: l.highlightConditions),
                          _Highlight(icon: Icons.verified_outlined, text: l.highlightSignals),
                          _Highlight(icon: Icons.shield_outlined, text: l.highlightRisk, last: true),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: ZxSpace.xxl),
                  FilledButton.icon(
                    onPressed: _busy || !google.available ? null : () => _run(notifier.signInWithGoogle),
                    icon: const Icon(Icons.account_circle_outlined),
                    label: Text(l.signInWithGoogle),
                  ),
                  if (!google.available) ...[
                    const SizedBox(height: ZxSpace.sm),
                    Text(l.googleNotConfigured, style: t.caption, textAlign: TextAlign.center),
                  ],
                  if (config.devLogin) ...[
                    const SizedBox(height: ZxSpace.xxl),
                    GlassCard(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Text(l.devSignIn, style: t.bodyStrong),
                          const SizedBox(height: ZxSpace.xs),
                          Text(l.devSignInHint, style: t.caption),
                          const SizedBox(height: ZxSpace.md),
                          TextField(
                            key: const Key('devEmail'),
                            controller: _email,
                            keyboardType: TextInputType.emailAddress,
                            decoration: InputDecoration(labelText: l.email),
                          ),
                          const SizedBox(height: ZxSpace.md),
                          OutlinedButton(
                            key: const Key('devSignIn'),
                            onPressed: _busy ? null : () => _run(() => notifier.signInDev(_email.text)),
                            child: Text(l.devSignIn),
                          ),
                        ],
                      ),
                    ),
                  ],
                  const SizedBox(height: ZxSpace.lg),
                  TextButton(
                    key: const Key('guest'),
                    onPressed: _busy ? null : notifier.continueAsGuest,
                    child: Text(l.continueAsGuest),
                  ),
                  const SizedBox(height: ZxSpace.lg),
                  Text(l.legalNote, style: t.caption, textAlign: TextAlign.center),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _Highlight extends StatelessWidget {
  const _Highlight({required this.icon, required this.text, this.last = false});

  final IconData icon;
  final String text;
  final bool last;

  @override
  Widget build(BuildContext context) {
    final p = context.zx.palette;
    return Padding(
      padding: EdgeInsets.only(bottom: last ? 0 : ZxSpace.lg),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: ZxSize.tapTarget * 0.8,
            height: ZxSize.tapTarget * 0.8,
            decoration: BoxDecoration(color: p.accentSoft, borderRadius: BorderRadius.circular(ZxRadius.md)),
            child: Icon(icon, color: p.accent, size: ZxSize.iconLg),
          ),
          const SizedBox(width: ZxSpace.md),
          Expanded(child: Text(text, style: context.zx.text.secondary)),
        ],
      ),
    );
  }
}

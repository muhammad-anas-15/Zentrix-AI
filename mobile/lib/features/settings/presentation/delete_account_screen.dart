import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/l10n.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/theme/theme.dart';
import '../../../core/theme/tokens.dart';
import '../../../core/widgets/surfaces.dart';
import '../../auth/application/session.dart';

/// In-app account deletion (Google Play requirement): explains what is deleted and asks the user to type DELETE.
class DeleteAccountScreen extends ConsumerStatefulWidget {
  const DeleteAccountScreen({super.key});

  static const confirmWord = 'DELETE';

  @override
  ConsumerState<DeleteAccountScreen> createState() => _DeleteAccountScreenState();
}

class _DeleteAccountScreenState extends ConsumerState<DeleteAccountScreen> {
  final _confirm = TextEditingController();
  bool _busy = false;

  @override
  void dispose() {
    _confirm.dispose();
    super.dispose();
  }

  Future<void> _delete() async {
    setState(() => _busy = true);
    final l = context.l10n;
    final messenger = ScaffoldMessenger.of(context);
    try {
      // On success the session ends and the router leaves this screen.
      await ref.read(sessionProvider.notifier).deleteAccount();
    } on ApiException catch (e) {
      messenger.showSnackBar(SnackBar(content: Text(e.isNetwork ? l.errorNetwork : e.message)));
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final zx = context.zx;
    final confirmed = _confirm.text.trim() == DeleteAccountScreen.confirmWord;
    return ZxPage(
      title: l.deleteAccountTitle,
      children: [
        GlassCard(
          accent: zx.palette.bearish,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Icon(Icons.warning_amber_rounded, size: ZxSize.iconXl, color: zx.palette.bearish),
              const SizedBox(height: ZxSpace.md),
              Text(l.deleteAccountBody, style: zx.text.body),
              const SizedBox(height: ZxSpace.lg),
              TextField(
                key: const Key('confirmDelete'),
                controller: _confirm,
                autocorrect: false,
                textCapitalization: TextCapitalization.characters,
                decoration: InputDecoration(labelText: l.deleteAccountConfirmHint),
                onChanged: (_) => setState(() {}),
              ),
              const SizedBox(height: ZxSpace.lg),
              FilledButton(
                key: const Key('confirmDeleteButton'),
                style: FilledButton.styleFrom(backgroundColor: zx.palette.bearish),
                onPressed: confirmed && !_busy ? _delete : null,
                child: Text(l.deleteAccountButton),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/format/formatters.dart';
import '../../../core/l10n.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/theme/tokens.dart';
import '../../../core/widgets/surfaces.dart';
import '../../market/application/market_providers.dart';
import '../data/journal_repository.dart';
import '../domain/models.dart';

/// Log a trade (Premium: journal). The server computes P&L and R.
class TradeFormScreen extends ConsumerStatefulWidget {
  const TradeFormScreen({super.key});

  @override
  ConsumerState<TradeFormScreen> createState() => _TradeFormScreenState();
}

class _TradeFormScreenState extends ConsumerState<TradeFormScreen> {
  final _form = GlobalKey<FormState>();
  final _quantity = TextEditingController(text: '10000');
  final _entry = TextEditingController();
  final _stop = TextEditingController();
  final _tp = TextEditingController();
  final _notes = TextEditingController();
  String _symbol = defaultSymbols.first;
  String _side = 'long';
  DateTime _entryAt = DateTime.now();
  bool _saving = false;

  @override
  void dispose() {
    for (final c in [_quantity, _entry, _stop, _tp, _notes]) {
      c.dispose();
    }
    super.dispose();
  }

  static double? _num(String s) => double.tryParse(s.trim().replaceAll(',', ''));

  Future<void> _pickTime() async {
    final date = await showDatePicker(
      context: context,
      initialDate: _entryAt,
      firstDate: DateTime.now().subtract(const Duration(days: 365 * 5)),
      lastDate: DateTime.now(),
    );
    if (date == null || !mounted) return;
    final time = await showTimePicker(context: context, initialTime: TimeOfDay.fromDateTime(_entryAt));
    if (time == null) return;
    setState(() => _entryAt = DateTime(date.year, date.month, date.day, time.hour, time.minute));
  }

  Future<void> _save() async {
    if (!_form.currentState!.validate()) return;
    setState(() => _saving = true);
    final l = context.l10n;
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ref
          .read(journalRepositoryProvider)
          .create(
            NewTrade(
              symbol: _symbol,
              side: _side,
              quantity: _num(_quantity.text)!,
              entryPrice: _num(_entry.text)!,
              entryAt: _entryAt.toUtc(),
              stopLoss: _num(_stop.text),
              takeProfit: _num(_tp.text),
              notes: _notes.text.trim().isEmpty ? null : _notes.text.trim(),
            ),
          );
      ref.invalidate(journalProvider);
      messenger.showSnackBar(SnackBar(content: Text(l.tradeSaved)));
      if (mounted) context.pop();
    } on ApiException catch (e) {
      messenger.showSnackBar(SnackBar(content: Text(e.isNetwork ? l.errorNetwork : e.message)));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    String? positive(String? v, {bool optional = false}) {
      if (v == null || v.trim().isEmpty) return optional ? null : l.fieldRequired;
      final n = _num(v);
      return n == null || n <= 0 ? l.invalidNumber : null;
    }

    final numbers = <TextInputFormatter>[FilteringTextInputFormatter.allow(RegExp(r'[0-9.,]'))];
    const keyboard = TextInputType.numberWithOptions(decimal: true);
    return ZxPage(
      title: l.addTrade,
      children: [
        Form(
          key: _form,
          child: GlassCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                DropdownButtonFormField<String>(
                  initialValue: _symbol,
                  decoration: InputDecoration(labelText: l.symbol),
                  items: [for (final s in defaultSymbols) DropdownMenuItem(value: s, child: Text(s))],
                  onChanged: (v) => setState(() => _symbol = v ?? _symbol),
                ),
                const SizedBox(height: ZxSpace.md),
                SegmentedButton<String>(
                  segments: [
                    ButtonSegment(value: 'long', label: Text(l.sideLong)),
                    ButtonSegment(value: 'short', label: Text(l.sideShort)),
                  ],
                  selected: {_side},
                  showSelectedIcon: false,
                  onSelectionChanged: (s) => setState(() => _side = s.first),
                ),
                const SizedBox(height: ZxSpace.md),
                TextFormField(
                  controller: _quantity,
                  keyboardType: keyboard,
                  inputFormatters: numbers,
                  decoration: InputDecoration(labelText: l.quantity, helperText: l.quantityHint),
                  validator: positive,
                ),
                const SizedBox(height: ZxSpace.md),
                TextFormField(
                  controller: _entry,
                  keyboardType: keyboard,
                  inputFormatters: numbers,
                  decoration: InputDecoration(labelText: l.entryPrice),
                  validator: positive,
                ),
                const SizedBox(height: ZxSpace.md),
                OutlinedButton.icon(
                  onPressed: _pickTime,
                  icon: const Icon(Icons.schedule),
                  label: Text('${l.entryTime}: ${Fmt.dateTime(_entryAt, context.localeCode)}'),
                ),
                const SizedBox(height: ZxSpace.md),
                Row(
                  children: [
                    Expanded(
                      child: TextFormField(
                        controller: _stop,
                        keyboardType: keyboard,
                        inputFormatters: numbers,
                        decoration: InputDecoration(labelText: l.stopLoss),
                        validator: (v) => positive(v, optional: true),
                      ),
                    ),
                    const SizedBox(width: ZxSpace.md),
                    Expanded(
                      child: TextFormField(
                        controller: _tp,
                        keyboardType: keyboard,
                        inputFormatters: numbers,
                        decoration: InputDecoration(labelText: l.takeProfitOptional),
                        validator: (v) => positive(v, optional: true),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: ZxSpace.md),
                TextFormField(
                  controller: _notes,
                  maxLines: 3,
                  maxLength: 500,
                  decoration: InputDecoration(labelText: l.notes),
                ),
                const SizedBox(height: ZxSpace.md),
                FilledButton(onPressed: _saving ? null : _save, child: Text(l.save)),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/format/formatters.dart';
import '../../../core/l10n.dart';
import '../../../core/theme/theme.dart';
import '../../../core/theme/tokens.dart';
import '../../../core/widgets/badges.dart';
import '../../../core/widgets/states.dart';
import '../../../core/widgets/surfaces.dart';
import '../../auth/application/session.dart';
import '../../market/application/market_providers.dart';
import '../data/risk_repository.dart';
import '../domain/models.dart';

const accountCurrencies = <String>['USD', 'EUR', 'GBP', 'JPY', 'CHF', 'AUD', 'CAD', 'NZD', 'USDT'];

/// Position size, money at risk, pip value, R:R and margin. Sizes are rounded down by the server.
class CalculatorScreen extends ConsumerStatefulWidget {
  const CalculatorScreen({super.key});

  @override
  ConsumerState<CalculatorScreen> createState() => _CalculatorScreenState();
}

class _CalculatorScreenState extends ConsumerState<CalculatorScreen> {
  final _form = GlobalKey<FormState>();
  final _balance = TextEditingController();
  final _riskPct = TextEditingController(text: '1');
  final _entry = TextEditingController();
  final _stop = TextEditingController();
  final _tp = TextEditingController();
  final _leverage = TextEditingController();
  String _symbol = defaultSymbols.first;
  String? _currency;
  AsyncValue<PositionSize>? _result;

  @override
  void dispose() {
    for (final c in [_balance, _riskPct, _entry, _stop, _tp, _leverage]) {
      c.dispose();
    }
    super.dispose();
  }

  static double? _num(String s) => double.tryParse(s.trim().replaceAll(',', ''));

  Future<void> _calculate() async {
    if (!_form.currentState!.validate()) return;
    FocusScope.of(context).unfocus();
    final request = PositionSizeRequest(
      symbol: _symbol,
      entry: _num(_entry.text)!,
      stop: _num(_stop.text)!,
      takeProfit: _num(_tp.text),
      accountCurrency: _currency,
      balance: _num(_balance.text),
      riskPct: _num(_riskPct.text),
      leverage: _num(_leverage.text),
    );
    setState(() => _result = const AsyncLoading());
    final next = await AsyncValue.guard(() => ref.read(riskRepositoryProvider).positionSize(request));
    if (mounted) setState(() => _result = next);
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final signedIn = ref.watch(currentUserProvider) != null;
    String? positive(String? v, {bool optional = false}) {
      if (v == null || v.trim().isEmpty) return optional ? null : l.fieldRequired;
      final n = _num(v);
      return n == null || n <= 0 ? l.invalidNumber : null;
    }

    final numberField = <TextInputFormatter>[FilteringTextInputFormatter.allow(RegExp(r'[0-9.,]'))];
    const numberKeyboard = TextInputType.numberWithOptions(decimal: true);

    return ZxPage(
      title: l.riskTitle,
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
                Row(
                  children: [
                    Expanded(
                      child: DropdownButtonFormField<String?>(
                        initialValue: _currency,
                        decoration: InputDecoration(labelText: l.accountCurrency),
                        items: [
                          DropdownMenuItem(value: null, child: Text(signedIn ? l.fromProfileShort : 'USD')),
                          for (final c in accountCurrencies) DropdownMenuItem(value: c, child: Text(c)),
                        ],
                        onChanged: (v) => setState(() => _currency = v),
                      ),
                    ),
                    const SizedBox(width: ZxSpace.md),
                    Expanded(
                      child: TextFormField(
                        key: const Key('balance'),
                        controller: _balance,
                        keyboardType: numberKeyboard,
                        inputFormatters: numberField,
                        decoration: InputDecoration(
                          labelText: l.balance,
                          helperText: signedIn ? l.fromProfileHint : null,
                        ),
                        validator: (v) => positive(v, optional: signedIn),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: ZxSpace.md),
                TextFormField(
                  key: const Key('riskPct'),
                  controller: _riskPct,
                  keyboardType: numberKeyboard,
                  inputFormatters: numberField,
                  decoration: InputDecoration(labelText: l.riskPct),
                  validator: (v) => positive(v, optional: signedIn),
                ),
                const SizedBox(height: ZxSpace.md),
                Row(
                  children: [
                    Expanded(
                      child: TextFormField(
                        key: const Key('entry'),
                        controller: _entry,
                        keyboardType: numberKeyboard,
                        inputFormatters: numberField,
                        decoration: InputDecoration(labelText: l.entryPrice),
                        validator: positive,
                      ),
                    ),
                    const SizedBox(width: ZxSpace.md),
                    Expanded(
                      child: TextFormField(
                        key: const Key('stop'),
                        controller: _stop,
                        keyboardType: numberKeyboard,
                        inputFormatters: numberField,
                        decoration: InputDecoration(labelText: l.stopLoss),
                        validator: positive,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: ZxSpace.md),
                Row(
                  children: [
                    Expanded(
                      child: TextFormField(
                        controller: _tp,
                        keyboardType: numberKeyboard,
                        inputFormatters: numberField,
                        decoration: InputDecoration(labelText: l.takeProfitOptional),
                        validator: (v) => positive(v, optional: true),
                      ),
                    ),
                    const SizedBox(width: ZxSpace.md),
                    Expanded(
                      child: TextFormField(
                        controller: _leverage,
                        keyboardType: numberKeyboard,
                        inputFormatters: numberField,
                        decoration: InputDecoration(labelText: l.leverageOptional),
                        validator: (v) => positive(v, optional: true),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: ZxSpace.lg),
                FilledButton(
                  key: const Key('calculate'),
                  onPressed: _result is AsyncLoading ? null : _calculate,
                  child: Text(l.calculate),
                ),
              ],
            ),
          ),
        ),
        if (_result != null)
          AsyncValueView<PositionSize>(
            value: _result!,
            onRetry: _calculate,
            data: (r) => SizeResult(result: r),
          ),
        const Disclaimer(),
      ],
    );
  }
}

/// The calculator's answer.
class SizeResult extends StatelessWidget {
  const SizeResult({super.key, required this.result});

  final PositionSize result;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final zx = context.zx;
    final r = result;
    final cur = r.accountCurrency;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        GlassCard(
          accent: zx.palette.accent,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text('${r.symbol} · ${r.side == 'long' ? l.sideLong : l.sideShort}', style: zx.text.label),
                  ),
                ],
              ),
              const SizedBox(height: ZxSpace.sm),
              Text(
                r.lots != null
                    ? '${Fmt.number(r.lots, decimals: 2)} ${l.resultLots}'
                    : '${Fmt.number(r.units, decimals: 4)} ${l.resultUnits}',
                key: const Key('sizeHeadline'),
                style: zx.text.price,
              ),
              Text('${Fmt.number(r.units, decimals: 0)} ${l.resultUnits}', style: zx.text.caption),
              const SizedBox(height: ZxSpace.lg),
              MetricGrid(
                tiles: [
                  MetricTile(
                    label: l.resultRisk,
                    value: Fmt.money(r.riskAmount, cur),
                    valueColor: zx.palette.bearish,
                    caption: r.riskPct == null ? null : Fmt.ratio(r.riskPct! / 100, decimals: 2),
                  ),
                  MetricTile(
                    label: l.resultStop,
                    value: r.stopPips != null ? l.pips(Fmt.number(r.stopPips, decimals: 1)) : Fmt.price(r.stopDistance),
                    caption: r.stopAtr == null ? null : '${Fmt.number(r.stopAtr, decimals: 2)} ATR',
                  ),
                  if (r.pipValuePerLot != null)
                    MetricTile(label: l.resultPipValue, value: Fmt.money(r.pipValuePerLot, cur)),
                  if (r.riskReward != null)
                    MetricTile(
                      label: l.resultRR,
                      value: '${Fmt.number(r.riskReward, decimals: 2)} : 1',
                      valueColor: r.riskReward! >= 1 ? zx.palette.bullish : zx.palette.caution,
                    ),
                  if (r.rewardAmount != null)
                    MetricTile(
                      label: l.resultReward,
                      value: Fmt.money(r.rewardAmount, cur),
                      valueColor: zx.palette.bullish,
                    ),
                  if (r.margin != null) MetricTile(label: l.resultMargin, value: Fmt.money(r.margin, cur)),
                  if (r.dailyLossLeft != null)
                    MetricTile(label: l.resultDailyLeft, value: Fmt.money(r.dailyLossLeft, cur)),
                ],
              ),
            ],
          ),
        ),
        if (r.premiumLocked.contains('risk_guard')) ...[
          const SizedBox(height: ZxSpace.md),
          GlassCard(
            child: Row(
              children: [
                Expanded(child: Text(l.dailyLossPremium, style: zx.text.caption)),
                const PremiumBadge(),
              ],
            ),
          ),
        ],
        if (r.warnings.isNotEmpty) ...[
          const SizedBox(height: ZxSpace.md),
          GlassCard(
            accent: zx.palette.caution,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(l.warnings, style: zx.text.bodyStrong.copyWith(color: zx.palette.caution)),
                for (final w in r.warnings) ...[
                  const SizedBox(height: ZxSpace.xs),
                  Text('• $w', style: zx.text.secondary),
                ],
              ],
            ),
          ),
        ],
        if (r.conversionNotes.isNotEmpty) ...[
          const SizedBox(height: ZxSpace.md),
          Text('${l.conversion}: ${r.conversionNotes.join('; ')}', style: zx.text.caption),
        ],
      ],
    );
  }
}

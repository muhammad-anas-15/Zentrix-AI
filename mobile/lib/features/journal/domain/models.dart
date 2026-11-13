import 'package:freezed_annotation/freezed_annotation.dart';

import '../../../core/models/premium.dart';

part 'models.freezed.dart';
part 'models.g.dart';

/// A journal trade. P&L and R are computed by the server.
@freezed
abstract class JournalEntry with _$JournalEntry {
  const JournalEntry._();

  const factory JournalEntry({
    required int id,
    required String symbol,
    required String side,
    required String status,
    required double quantity,
    required double entryPrice,
    required DateTime entryAt,
    double? exitPrice,
    DateTime? exitAt,
    double? stopLoss,
    double? takeProfit,
    @Default(0) double fees,
    required String accountCurrency,
    double? riskAccount,
    double? pnlQuote,
    double? pnlAccount,
    double? rMultiple,
    String? timeframe,
    int? signalId,
    String? setup,
    @Default(<String>[]) List<String> tags,
    String? notes,
    @Default(<String>[]) List<String> calcNotes,
  }) = _JournalEntry;

  factory JournalEntry.fromJson(Map<String, dynamic> json) => _$JournalEntryFromJson(json);

  bool get isOpen => status == 'open';
}

@freezed
abstract class JournalPage with _$JournalPage {
  const factory JournalPage({required List<JournalEntry> items, int? nextBeforeId, PremiumBadge? premium}) =
      _JournalPage;

  factory JournalPage.fromJson(Map<String, dynamic> json) => _$JournalPageFromJson(json);
}

/// Input of `POST /v1/journal`.
@freezed
abstract class NewTrade with _$NewTrade {
  const factory NewTrade({
    required String symbol,
    required String side,
    required double quantity,
    required double entryPrice,
    required DateTime entryAt,
    double? stopLoss,
    double? takeProfit,
    double? exitPrice,
    DateTime? exitAt,
    String? notes,
  }) = _NewTrade;

  factory NewTrade.fromJson(Map<String, dynamic> json) => _$NewTradeFromJson(json);
}

/// `GET /v1/journal/stats` (Premium: journal).
@freezed
abstract class JournalStats with _$JournalStats {
  const factory JournalStats({
    required String accountCurrency,
    required int trades,
    required int open,
    required int closed,
    required int counted,
    required int wins,
    required int losses,
    required int breakeven,
    double? winRate,
    required double netPnl,
    double? avgWin,
    double? avgLoss,
    double? profitFactor,
    double? expectancy,
    double? avgR,
    required int maxConsecutiveLosses,
    PremiumBadge? premium,
  }) = _JournalStats;

  factory JournalStats.fromJson(Map<String, dynamic> json) => _$JournalStatsFromJson(json);
}

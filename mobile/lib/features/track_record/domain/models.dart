import 'package:freezed_annotation/freezed_annotation.dart';

part 'models.freezed.dart';
part 'models.g.dart';

/// Outcome counts. The hit rate excludes flat and void outcomes (both are reported).
@freezed
abstract class OutcomeCounts with _$OutcomeCounts {
  const factory OutcomeCounts({
    required int signals,
    required int pending,
    required int decided,
    required int wins,
    required int losses,
    required int flats,
    required int voids,
    double? hitRate,
    List<double?>? ci95,
    String? strength,
  }) = _OutcomeCounts;

  factory OutcomeCounts.fromJson(Map<String, dynamic> json) => _$OutcomeCountsFromJson(json);
}

/// `GET /v1/track-record`: computed live from stored signals and outcomes.
@freezed
abstract class TrackRecord with _$TrackRecord {
  const factory TrackRecord({
    required OutcomeCounts overall,
    @Default(<OutcomeCounts>[]) List<OutcomeCounts> byStrength,
    DateTime? firstSignalAt,
    DateTime? lastSignalAt,
    String? method,
    String? disclaimer,
  }) = _TrackRecord;

  factory TrackRecord.fromJson(Map<String, dynamic> json) => _$TrackRecordFromJson(json);
}

import 'package:freezed_annotation/freezed_annotation.dart';

part 'premium.freezed.dart';
part 'premium.g.dart';

/// "Premium" label the API puts on premium features. A label, not a lock.
@freezed
abstract class PremiumBadge with _$PremiumBadge {
  const factory PremiumBadge({required String feature, @Default('Premium') String label}) = _PremiumBadge;

  factory PremiumBadge.fromJson(Map<String, dynamic> json) => _$PremiumBadgeFromJson(json);
}

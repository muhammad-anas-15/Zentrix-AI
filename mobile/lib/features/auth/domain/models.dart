import 'package:freezed_annotation/freezed_annotation.dart';

part 'models.freezed.dart';
part 'models.g.dart';

/// `GET /v1/me`.
@freezed
abstract class AppUser with _$AppUser {
  const factory AppUser({
    required String id,
    String? email,
    String? displayName,
    String? avatarUrl,
    required String plan,
    required bool premiumAccess,
    DateTime? premiumUntil,
    required String locale,
    required String timezone,
    required DateTime createdAt,
  }) = _AppUser;

  factory AppUser.fromJson(Map<String, dynamic> json) => _$AppUserFromJson(json);
}

/// Token response of sign-in and refresh.
@freezed
abstract class TokenResponse with _$TokenResponse {
  const factory TokenResponse({
    required String accessToken,
    required String refreshToken,
    required int expiresIn,
    required AppUser user,
  }) = _TokenResponse;

  factory TokenResponse.fromJson(Map<String, dynamic> json) => _$TokenResponseFromJson(json);
}

@freezed
abstract class FeatureAccess with _$FeatureAccess {
  const factory FeatureAccess({
    required String key,
    required String tier,
    required bool available,
    String? via,
    DateTime? until,
  }) = _FeatureAccess;

  factory FeatureAccess.fromJson(Map<String, dynamic> json) => _$FeatureAccessFromJson(json);
}

@freezed
abstract class FreeMarkets with _$FreeMarkets {
  const factory FreeMarkets({required List<String> symbols, required List<String> timeframes}) = _FreeMarkets;

  factory FreeMarkets.fromJson(Map<String, dynamic> json) => _$FreeMarketsFromJson(json);
}

/// `GET /v1/me/access`: effective plan and per-feature availability.
@freezed
abstract class Access with _$Access {
  const factory Access({
    required String plan,
    String? source,
    DateTime? premiumUntil,
    required bool premiumAccess,
    required bool enforced,
    required FreeMarkets freeMarkets,
    required List<FeatureAccess> features,
  }) = _Access;

  factory Access.fromJson(Map<String, dynamic> json) => _$AccessFromJson(json);
}

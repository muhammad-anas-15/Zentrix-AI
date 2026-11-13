import 'package:dio/dio.dart';

/// Every API failure as one type. The backend always answers
/// `{"error": {"code": "...", "message": "...", "details": ...}}`.
class ApiException implements Exception {
  const ApiException({required this.code, required this.message, this.status, this.details});

  factory ApiException.fromDio(DioException e) {
    final response = e.response;
    if (response == null) {
      return ApiException(code: 'network', message: e.message ?? 'network error');
    }
    final data = response.data;
    if (data is Map<String, dynamic> && data['error'] is Map<String, dynamic>) {
      final err = data['error'] as Map<String, dynamic>;
      return ApiException(
        status: response.statusCode,
        code: (err['code'] as String?) ?? 'http_error',
        message: (err['message'] as String?) ?? 'request failed',
        details: err['details'],
      );
    }
    return ApiException(status: response.statusCode, code: 'http_error', message: 'HTTP ${response.statusCode}');
  }

  final int? status;
  final String code;
  final String message;
  final Object? details;

  bool get isNetwork => code == 'network';
  bool get isUnauthorized => status == 401;
  bool get isNotFound => status == 404;

  /// The server enforces premium and the caller lacks the feature (only while PREMIUM_ENFORCED=true).
  bool get isPremiumRequired => code == 'premium_required';

  /// Premium feature key from `details.feature`, when present.
  String? get premiumFeature {
    final d = details;
    return d is Map<String, dynamic> ? d['feature'] as String? : null;
  }

  /// Validation problems or "no data" style answers that retrying will not fix.
  bool get isPermanent => status != null && status! >= 400 && status! < 500 && status != 429;

  @override
  String toString() => 'ApiException($status $code: $message)';
}

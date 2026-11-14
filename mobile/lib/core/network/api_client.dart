import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart' show visibleForTesting;

import '../storage/token_store.dart';
import 'api_exception.dart';

typedef Parse<T> = T Function(Object? json);

/// HTTP client for the Zentrix API: bearer auth, one serialized token refresh, typed errors.
///
/// Refresh tokens are single-use on the server (re-using one revokes the whole session), so a burst of
/// 401s must refresh exactly once: the interceptor is queued, and a request that failed with an access
/// token that has since been replaced is simply retried with the new one.
class ApiClient {
  ApiClient({required String baseUrl, required this.tokens, HttpClientAdapter? adapter})
    : dio = Dio(_options(baseUrl)),
      _bare = Dio(_options(baseUrl)) {
    if (adapter != null) {
      dio.httpClientAdapter = adapter;
      _bare.httpClientAdapter = adapter;
    }
    dio.interceptors.add(_AuthInterceptor(this));
  }

  static BaseOptions _options(String baseUrl) => BaseOptions(
    baseUrl: baseUrl,
    connectTimeout: const Duration(seconds: 10),
    receiveTimeout: const Duration(seconds: 30),
    headers: <String, Object>{'Accept': 'application/json'},
  );

  final Dio dio;

  /// No interceptors: refresh calls and retries. Retrying through [dio] from inside the queued
  /// interceptor would deadlock if the retry failed too.
  final Dio _bare;
  final TokenStore tokens;
  final StreamController<void> _expired = StreamController<void>.broadcast();

  /// Fires when the session can no longer be refreshed (revoked, reused or expired refresh token).
  Stream<void> get sessionExpired => _expired.stream;

  /// GETs are retried once after a dropped connection (common on mobile networks); writes never are.
  Future<T> get<T>(String path, Parse<T> parse, {Map<String, Object?>? query}) =>
      _send(() => dio.get<Object?>(path, queryParameters: _clean(query)), parse, retryOnce: true);

  Future<T> post<T>(String path, Parse<T> parse, {Object? body, bool auth = true}) => _send(
    () => dio.post<Object?>(
      path,
      data: body,
      options: Options(extra: <String, Object>{'auth': auth}),
    ),
    parse,
  );

  Future<T> put<T>(String path, Parse<T> parse, {Object? body}) =>
      _send(() => dio.put<Object?>(path, data: body), parse);

  Future<T> patch<T>(String path, Parse<T> parse, {Object? body}) =>
      _send(() => dio.patch<Object?>(path, data: body), parse);

  Future<void> delete(String path, {Map<String, Object?>? query}) =>
      _send(() => dio.delete<Object?>(path, queryParameters: _clean(query)), (_) {});

  static const retryDelay = Duration(milliseconds: 400);

  Future<T> _send<T>(Future<Response<Object?>> Function() call, Parse<T> parse, {bool retryOnce = false}) async {
    try {
      final response = await call();
      return parse(response.data);
    } on DioException catch (e) {
      if (retryOnce && e.response == null && e.type != DioExceptionType.cancel) {
        await Future<void>.delayed(retryDelay);
        return _send(call, parse);
      }
      throw ApiException.fromDio(e);
    }
  }

  static Map<String, Object?>? _clean(Map<String, Object?>? q) =>
      q == null ? null : (Map<String, Object?>.of(q)..removeWhere((_, v) => v == null));

  Future<Tokens> _refresh(String refreshToken) async {
    final res = await _bare.post<Map<String, dynamic>>(
      '/v1/auth/refresh',
      data: <String, String>{'refresh_token': refreshToken},
    );
    final data = res.data!;
    final next = Tokens(access: data['access_token'] as String, refresh: data['refresh_token'] as String);
    await tokens.write(next);
    return next;
  }

  void _notifyExpired() {
    if (!_expired.isClosed) _expired.add(null);
  }

  @visibleForTesting
  void debugNotifyExpired() => _notifyExpired();

  Future<void> close() async {
    await _expired.close();
    dio.close();
    _bare.close();
  }
}

class _AuthInterceptor extends QueuedInterceptor {
  _AuthInterceptor(this.client);

  final ApiClient client;
  static const _refreshable = {'token_expired', 'invalid_token'};

  @override
  Future<void> onRequest(RequestOptions options, RequestInterceptorHandler handler) async {
    if (options.extra['auth'] != false) {
      final t = await client.tokens.read();
      if (t != null) options.headers['Authorization'] = 'Bearer ${t.access}';
    }
    handler.next(options);
  }

  @override
  Future<void> onError(DioException err, ErrorInterceptorHandler handler) async {
    final req = err.requestOptions;
    final sent = req.headers['Authorization'] as String?;
    final code = ApiException.fromDio(err).code;
    if (err.response?.statusCode != 401 || sent == null || req.extra['retried'] == true) {
      return handler.next(err);
    }
    if (!_refreshable.contains(code)) {
      // token_revoked (logout-all) or an unknown account: the session is over
      await client.tokens.clear();
      client._notifyExpired();
      return handler.next(err);
    }
    var current = await client.tokens.read();
    if (current == null) return handler.next(err);
    if ('Bearer ${current.access}' == sent) {
      try {
        current = await client._refresh(current.refresh);
      } on DioException catch (e) {
        if (e.response?.statusCode == 401) {
          await client.tokens.clear();
          client._notifyExpired();
        }
        return handler.next(err);
      }
    }
    try {
      final retry = req.copyWith(
        headers: <String, dynamic>{...req.headers, 'Authorization': 'Bearer ${current.access}'},
        extra: <String, dynamic>{...req.extra, 'retried': true},
      );
      handler.resolve(await client._bare.fetch<Object?>(retry));
    } on DioException catch (e) {
      handler.next(e);
    }
  }
}

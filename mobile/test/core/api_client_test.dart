import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:zentrix/core/network/api_client.dart';
import 'package:zentrix/core/network/api_exception.dart';
import 'package:zentrix/core/storage/token_store.dart';

/// A tiny fake backend: `/v1/me` needs the current access token; `/v1/auth/refresh` rotates once per token.
class FakeServer implements HttpClientAdapter {
  FakeServer({this.validAccess = 'access-2', this.refreshOk = true});

  String validAccess;
  bool refreshOk;
  int refreshCalls = 0;
  final List<String> seen = [];

  ResponseBody _json(int status, Object body) => ResponseBody.fromString(
    jsonEncode(body),
    status,
    headers: {
      Headers.contentTypeHeader: [Headers.jsonContentType],
    },
  );

  ResponseBody _error(int status, String code) => _json(status, {
    'error': {'code': code, 'message': code},
  });

  @override
  Future<ResponseBody> fetch(RequestOptions o, Stream<Uint8List>? body, Future<void>? cancel) async {
    seen.add('${o.method} ${o.path}');
    await Future<void>.delayed(const Duration(milliseconds: 5));
    if (o.path == '/v1/auth/refresh') {
      refreshCalls++;
      if (!refreshOk) return _error(401, 'refresh_token_reused');
      return _json(200, {'access_token': validAccess, 'refresh_token': 'refresh-2'});
    }
    if (o.path == '/v1/missing') return _error(404, 'no_data');
    final auth = o.headers['Authorization'];
    if (auth != 'Bearer $validAccess') return _error(401, 'token_expired');
    return _json(200, {'ok': true});
  }

  @override
  void close({bool force = false}) {}
}

void main() {
  test('an expired access token is refreshed once and the request retried', () async {
    final server = FakeServer();
    final store = MemoryTokenStore(const Tokens(access: 'access-1', refresh: 'refresh-1'));
    final api = ApiClient(baseUrl: 'http://test', tokens: store, adapter: server);
    final result = await api.get('/v1/me', (j) => (j! as Map<String, dynamic>)['ok']);
    expect(result, true);
    expect(server.refreshCalls, 1);
    expect((await store.read())!.access, 'access-2');
  });

  test('a burst of 401s refreshes exactly once (refresh tokens are single-use)', () async {
    final server = FakeServer();
    final store = MemoryTokenStore(const Tokens(access: 'access-1', refresh: 'refresh-1'));
    final api = ApiClient(baseUrl: 'http://test', tokens: store, adapter: server);
    final results = await Future.wait([
      for (var i = 0; i < 5; i++) api.get('/v1/me', (j) => (j! as Map<String, dynamic>)['ok']),
    ]);
    expect(results, everyElement(true));
    expect(server.refreshCalls, 1);
  });

  test('a rejected refresh ends the session', () async {
    final server = FakeServer(refreshOk: false);
    final store = MemoryTokenStore(const Tokens(access: 'access-1', refresh: 'refresh-1'));
    final api = ApiClient(baseUrl: 'http://test', tokens: store, adapter: server);
    final expired = expectLater(api.sessionExpired, emits(null));
    await expectLater(api.get('/v1/me', (j) => j), throwsA(isA<ApiException>().having((e) => e.status, 'status', 401)));
    await expired;
    expect(await store.read(), isNull);
  });

  test('server errors become ApiException with the server code', () async {
    final api = ApiClient(baseUrl: 'http://test', tokens: MemoryTokenStore(), adapter: FakeServer());
    await expectLater(
      api.get('/v1/missing', (j) => j),
      throwsA(isA<ApiException>().having((e) => e.code, 'code', 'no_data').having((e) => e.isNotFound, '404', true)),
    );
  });

  test('premium_required exposes the feature', () {
    const e = ApiException(status: 403, code: 'premium_required', message: 'm', details: {'feature': 'scenario'});
    expect(e.isPremiumRequired, isTrue);
    expect(e.premiumFeature, 'scenario');
  });
}

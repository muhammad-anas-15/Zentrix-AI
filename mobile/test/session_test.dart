import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:zentrix/core/network/api_client.dart';
import 'package:zentrix/core/network/api_exception.dart';
import 'package:zentrix/core/providers.dart';
import 'package:zentrix/core/router/router.dart';
import 'package:zentrix/core/storage/token_store.dart';
import 'package:zentrix/features/auth/application/session.dart';
import 'package:zentrix/features/auth/data/auth_repository.dart';
import 'package:zentrix/features/auth/domain/models.dart';

class FakeAuth extends Fake implements AuthRepository {
  FakeAuth({this.meError});

  final ApiException? meError;

  @override
  Future<AppUser> me() async {
    if (meError != null) throw meError!;
    return AppUser(
      id: 'u1',
      plan: 'free',
      premiumAccess: true,
      locale: 'ur',
      timezone: 'UTC',
      createdAt: DateTime.utc(2026, 11),
    );
  }

  @override
  Future<TokenResponse> signInDev(String email) async => TokenResponse(
    accessToken: 'a2',
    refreshToken: 'r2',
    expiresIn: 900,
    user: AppUser(
      id: 'u2',
      plan: 'free',
      premiumAccess: true,
      locale: 'en',
      timezone: 'UTC',
      createdAt: DateTime.utc(2026, 11),
      email: email,
    ),
  );

  @override
  Future<void> logout(String refreshToken) async {}
}

class NoGoogle implements GoogleAuthGateway {
  @override
  bool get available => false;
  @override
  Future<String> idToken() => throw UnimplementedError();
  @override
  Future<void> signOut() async {}
}

Future<ProviderContainer> container({Tokens? tokens, ApiException? meError}) async {
  SharedPreferences.setMockInitialValues({});
  final c = ProviderContainer(
    overrides: [
      sharedPreferencesProvider.overrideWithValue(await SharedPreferences.getInstance()),
      tokenStoreProvider.overrideWithValue(MemoryTokenStore(tokens)),
      authRepositoryProvider.overrideWithValue(FakeAuth(meError: meError)),
      googleAuthProvider.overrideWithValue(NoGoogle()),
    ],
    retry: (_, _) => null,
  );
  addTearDown(c.dispose);
  return c;
}

Future<SessionState> settled(ProviderContainer c) async {
  c.read(sessionProvider);
  for (var i = 0; i < 20 && c.read(sessionProvider) is SessionLoading; i++) {
    await Future<void>.delayed(Duration.zero);
  }
  return c.read(sessionProvider);
}

void main() {
  test('no saved tokens: signed out', () async {
    expect(await settled(await container()), isA<SessionSignedOut>());
  });

  test('saved tokens: the session is restored from /v1/me', () async {
    final s = await settled(
      await container(
        tokens: const Tokens(access: 'a', refresh: 'r'),
      ),
    );
    expect(s, isA<SessionSignedIn>().having((x) => x.user.id, 'id', 'u1'));
  });

  test('server unreachable at start-up: offline, tokens kept', () async {
    final c = await container(
      tokens: const Tokens(access: 'a', refresh: 'r'),
      meError: const ApiException(code: 'network', message: 'down'),
    );
    expect(await settled(c), isA<SessionOffline>());
    expect(await c.read(tokenStoreProvider).read(), isNotNull);
  });

  test('a rejected session clears the tokens', () async {
    final c = await container(
      tokens: const Tokens(access: 'a', refresh: 'r'),
      meError: const ApiException(status: 401, code: 'token_revoked', message: 'revoked'),
    );
    expect(await settled(c), isA<SessionSignedOut>());
    expect(await c.read(tokenStoreProvider).read(), isNull);
  });

  test('developer sign-in stores tokens; sign-out clears them', () async {
    final c = await container();
    await settled(c);
    await c.read(sessionProvider.notifier).signInDev(' dev@example.com ');
    expect(c.read(sessionProvider), isA<SessionSignedIn>());
    expect((await c.read(tokenStoreProvider).read())!.access, 'a2');
    await c.read(sessionProvider.notifier).signOut();
    expect(c.read(sessionProvider), isA<SessionSignedOut>());
    expect(await c.read(tokenStoreProvider).read(), isNull);
  });

  test('when the API reports the session expired, the app signs out', () async {
    final c = await container(
      tokens: const Tokens(access: 'a', refresh: 'r'),
    );
    await settled(c);
    final api = c.read(apiClientProvider);
    // simulate a failed refresh inside the client
    unawaited(api.tokens.clear());
    final done = Completer<void>();
    c.listen(sessionProvider, (_, next) {
      if (next is SessionSignedOut && !done.isCompleted) done.complete();
    });
    debugExpireSession(api);
    await done.future;
    expect((c.read(sessionProvider) as SessionSignedOut).reason, SignedOutReason.expired);
  });

  test('router: restoring -> splash, signed out -> sign-in, inside the app otherwise', () {
    final user = SessionSignedIn(
      AppUser(id: 'u', plan: 'free', premiumAccess: true, locale: 'en', timezone: 'UTC', createdAt: DateTime.utc(2026)),
    );
    Uri u(String s) => Uri.parse(s);
    expect(redirectFor(const SessionLoading(), u('/home')), '/splash');
    expect(redirectFor(const SessionSignedOut(), u('/sign-in')), isNull);
    expect(redirectFor(const SessionGuest(), u('/sign-in')), '/home');
    expect(redirectFor(user, u('/splash')), '/home');
    expect(redirectFor(user, u('/pair?symbol=EUR%2FUSD')), isNull);
    // a deep link opened at start-up survives the splash and the sign-in screen
    final kept = redirectFor(const SessionLoading(), u('/pair?symbol=EUR%2FUSD'))!;
    expect(kept, startsWith('/splash?from='));
    expect(redirectFor(user, u(kept)), '/pair?symbol=EUR%2FUSD');
    final toSignIn = redirectFor(const SessionSignedOut(), u('/journal'))!;
    expect(redirectFor(const SessionGuest(), u(toSignIn)), '/journal');
    expect(redirectFor(user, u('/splash?from=https%3A%2F%2Fevil.example')), '/home'); // only in-app paths
  });
}

/// ApiClient emits sessionExpired when a refresh is rejected; simulate that.
void debugExpireSession(ApiClient api) => api.debugNotifyExpired();

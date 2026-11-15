import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/providers.dart';
import '../../../core/storage/token_store.dart';
import '../data/auth_repository.dart';
import '../domain/models.dart';

/// Why the user is on the sign-in screen (localized by the UI).
enum SignedOutReason { none, expired, deleted }

@immutable
sealed class SessionState {
  const SessionState();
}

/// Restoring a saved session at start-up.
class SessionLoading extends SessionState {
  const SessionLoading();
}

/// Start-up could not reach the server; tokens are kept.
class SessionOffline extends SessionState {
  const SessionOffline();
}

class SessionSignedOut extends SessionState {
  const SessionSignedOut([this.reason = SignedOutReason.none]);

  final SignedOutReason reason;
}

/// Exploring public features without an account.
class SessionGuest extends SessionState {
  const SessionGuest();
}

class SessionSignedIn extends SessionState {
  const SessionSignedIn(this.user);

  final AppUser user;
}

/// The app's session: restore, sign in (Google or developer), guest mode, sign out, delete account.
class SessionController extends Notifier<SessionState> {
  StreamSubscription<void>? _expired;

  @override
  SessionState build() {
    final api = ref.watch(apiClientProvider);
    _expired = api.sessionExpired.listen((_) => state = const SessionSignedOut(SignedOutReason.expired));
    ref.onDispose(() => _expired?.cancel());
    Future.microtask(restore);
    return const SessionLoading();
  }

  AuthRepository get _repo => ref.read(authRepositoryProvider);
  TokenStore get _store => ref.read(tokenStoreProvider);

  Future<void> restore() async {
    state = const SessionLoading();
    if (await _store.read() == null) {
      final config = ref.read(appConfigProvider);
      if (config.devLogin && config.devAutoSignIn.isNotEmpty) {
        try {
          return await signInDev(config.devAutoSignIn);
        } on ApiException {
          // fall through to the sign-in screen
        }
      }
      state = const SessionSignedOut();
      return;
    }
    try {
      state = SessionSignedIn(await _repo.me());
    } on ApiException catch (e) {
      if (e.isNetwork || (e.status ?? 0) >= 500) {
        state = const SessionOffline();
      } else {
        await _store.clear();
        state = const SessionSignedOut(SignedOutReason.expired);
      }
    }
  }

  Future<void> signInWithGoogle() async {
    final idToken = await ref.read(googleAuthProvider).idToken();
    await _complete(await _repo.signInWithGoogle(idToken, deviceName: 'zentrix-app'));
  }

  Future<void> signInDev(String email) async => _complete(await _repo.signInDev(email.trim()));

  Future<void> _complete(TokenResponse r) async {
    await _store.write(Tokens(access: r.accessToken, refresh: r.refreshToken));
    state = SessionSignedIn(r.user);
  }

  void continueAsGuest() => state = const SessionGuest();

  /// Leave guest mode for the sign-in screen.
  void goToSignIn() => state = const SessionSignedOut();

  void updateUser(AppUser user) {
    if (state is SessionSignedIn) state = SessionSignedIn(user);
  }

  Future<void> signOut() async {
    final tokens = await _store.read();
    if (tokens != null) {
      try {
        await _repo.logout(tokens.refresh);
      } on ApiException {
        // signing out locally is enough when the server is unreachable
      }
    }
    await _endLocally(SignedOutReason.none);
  }

  Future<void> signOutEverywhere() async {
    await _repo.logoutAll();
    await _endLocally(SignedOutReason.none);
  }

  /// Permanently deletes the account on the server (Google Play requirement), then signs out.
  Future<void> deleteAccount() async {
    await _repo.deleteAccount();
    await _endLocally(SignedOutReason.deleted);
  }

  Future<void> _endLocally(SignedOutReason reason) async {
    await _store.clear();
    try {
      await ref.read(googleAuthProvider).signOut();
    } on Object {
      // the Google session is best effort
    }
    state = SessionSignedOut(reason);
  }
}

final sessionProvider = NotifierProvider<SessionController, SessionState>(SessionController.new);

/// The signed-in user, or null (guest / signed out).
final currentUserProvider = Provider<AppUser?>((ref) {
  final s = ref.watch(sessionProvider);
  return s is SessionSignedIn ? s.user : null;
});

/// Plan and per-feature access of the signed-in user.
final accessProvider = FutureProvider.autoDispose<Access?>((ref) async {
  if (ref.watch(currentUserProvider) == null) return null;
  return ref.watch(authRepositoryProvider).access();
});

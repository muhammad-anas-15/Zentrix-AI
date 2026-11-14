import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/alerts/presentation/alerts_screen.dart';
import '../../features/auth/application/session.dart';
import '../../features/auth/presentation/sign_in_screen.dart';
import '../../features/auth/presentation/splash_screen.dart';
import '../../features/dashboard/presentation/dashboard_screen.dart';
import '../../features/journal/presentation/journal_screen.dart';
import '../../features/journal/presentation/trade_form_screen.dart';
import '../../features/market/application/market_providers.dart';
import '../../features/market/presentation/markets_screen.dart';
import '../../features/market/presentation/pair_screen.dart';
import '../../features/risk/presentation/calculator_screen.dart';
import '../../features/settings/presentation/delete_account_screen.dart';
import '../../features/settings/presentation/settings_screen.dart';
import '../l10n.dart';
import '../widgets/surfaces.dart';

/// Where each session state may be: restoring -> splash, signed out -> sign-in, guest/signed in -> the app.
/// A deep link opened during start-up (e.g. /pair?symbol=EUR%2FUSD) is kept in `from` and opened afterwards.
String? redirectFor(SessionState session, Uri uri) {
  final path = uri.path;
  final from = uri.queryParameters['from'];
  String keep(String target) =>
      path == '/' || path == '/home' ? target : '$target?from=${Uri.encodeComponent(uri.toString())}';
  return switch (session) {
    SessionLoading() || SessionOffline() => path == '/splash' ? null : keep('/splash'),
    SessionSignedOut() => path == '/sign-in' ? null : keep('/sign-in'),
    SessionGuest() || SessionSignedIn() =>
      path == '/splash' || path == '/sign-in' ? (from != null && from.startsWith('/') ? from : '/home') : null,
  };
}

final routerProvider = Provider<GoRouter>((ref) {
  final session = ValueNotifier<SessionState>(ref.read(sessionProvider));
  ref.listen<SessionState>(sessionProvider, (_, next) => session.value = next);
  final router = GoRouter(
    initialLocation: '/splash',
    refreshListenable: session,
    redirect: (context, state) => redirectFor(session.value, state.uri),
    routes: [
      GoRoute(path: '/splash', builder: (_, _) => const SplashScreen()),
      GoRoute(path: '/sign-in', builder: (_, _) => const SignInScreen()),
      StatefulShellRoute.indexedStack(
        builder: (context, state, shell) => HomeShell(shell: shell),
        branches: [
          StatefulShellBranch(
            routes: [GoRoute(path: '/home', builder: (_, _) => const DashboardScreen())],
          ),
          StatefulShellBranch(
            routes: [GoRoute(path: '/markets', builder: (_, _) => const MarketsScreen())],
          ),
          StatefulShellBranch(
            routes: [GoRoute(path: '/risk', builder: (_, _) => const CalculatorScreen())],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/journal',
                builder: (_, state) =>
                    JournalScreen(initialTab: (int.tryParse(state.uri.queryParameters['tab'] ?? '') ?? 0).clamp(0, 2)),
                routes: [GoRoute(path: 'new', builder: (_, _) => const TradeFormScreen())],
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/settings',
                builder: (_, _) => const SettingsScreen(),
                routes: [GoRoute(path: 'delete-account', builder: (_, _) => const DeleteAccountScreen())],
              ),
            ],
          ),
        ],
      ),
      GoRoute(
        path: '/pair',
        builder: (_, state) => PairScreen(
          symbol: state.uri.queryParameters['symbol'] ?? defaultSymbols.first,
          initialTimeframe: state.uri.queryParameters['tf'] ?? defaultTimeframe,
        ),
      ),
      GoRoute(path: '/alerts', builder: (_, _) => const AlertsScreen()),
    ],
  );
  ref.onDispose(() {
    router.dispose();
    session.dispose();
  });
  return router;
});

/// Bottom navigation: Home, Markets, Risk, Journal, Settings.
class HomeShell extends StatelessWidget {
  const HomeShell({super.key, required this.shell});

  final StatefulNavigationShell shell;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    return Scaffold(
      extendBody: true, // pages scroll under the frosted navigation bar
      body: shell,
      bottomNavigationBar: FrostedBar(
        edge: AxisDirection.up,
        child: NavigationBar(
          selectedIndex: shell.currentIndex,
          onDestinationSelected: (i) => shell.goBranch(i, initialLocation: i == shell.currentIndex),
          destinations: [
            NavigationDestination(icon: const Icon(Icons.space_dashboard_outlined), label: l.navHome),
            NavigationDestination(icon: const Icon(Icons.candlestick_chart_outlined), label: l.navMarkets),
            NavigationDestination(icon: const Icon(Icons.calculate_outlined), label: l.navRisk),
            NavigationDestination(icon: const Icon(Icons.menu_book_outlined), label: l.navJournal),
            NavigationDestination(icon: const Icon(Icons.tune), label: l.navSettings),
          ],
        ),
      ),
    );
  }
}

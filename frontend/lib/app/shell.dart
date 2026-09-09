import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/features/dashboard/screens/dashboard_screen.dart';
import 'package:patchpilot_web/features/repair/shell/repair_session.dart';
import 'package:patchpilot_web/features/repair/shell/repair_workflow.dart';
import 'package:patchpilot_web/features/repositories/screens/issues_screen.dart';
import 'package:patchpilot_web/models/models.dart';
import 'package:patchpilot_web/services/analysis_cache.dart';
import 'package:patchpilot_web/services/api_client.dart';
import 'package:patchpilot_web/services/browser_location.dart';
import 'package:patchpilot_web/services/github_redirect.dart';
import 'package:patchpilot_web/services/session_token.dart';

import 'app_routes.dart';

class AppShell extends StatefulWidget {
  final ApiClient? api;
  final GithubRedirect? redirect;
  final bool? refreshGrantsOnStart;
  final String? initialAuthError;

  const AppShell({
    super.key,
    this.api,
    this.redirect,
    this.refreshGrantsOnStart,
    this.initialAuthError,
  });

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  late final ApiClient _api;
  late final GithubRedirect _redirect;

  final _session = ValueNotifier<AuthUser?>(null);
  final _cache = AnalysisCache();

  GoRouter? _router;
  bool _authReady = false;

  @override
  void initState() {
    super.initState();
    _api = widget.api ?? ApiClient();
    _redirect = widget.redirect ?? GithubRedirect();
    _captureSessionFromRedirect();
    _loadSession();
  }

  void _captureSessionFromRedirect() {
    final location = BrowserLocation();
    final sessionId = sessionIdFromFragment(location.fragment);
    if (sessionId == null) return;
    _api.storeSessionToken(sessionId);
    location.replaceWithoutFragment();
  }

  @override
  void dispose() {
    _router?.dispose();
    _session.dispose();
    super.dispose();
  }

  Future<void> _loadSession() async {
    try {
      final me = await _api.getMe();
      if (!mounted) return;
      _session.value = me.authenticated ? me.user : null;
      setState(() => _authReady = true);
    } catch (_) {
      if (!mounted) return;
      _session.value = null;
      setState(() => _authReady = true);
    }
  }

  Future<void> _connectGithub() async {
    String? returnTo;
    final base = Uri.base;
    if (base.scheme == 'http' || base.scheme == 'https') {
      returnTo = base.origin;
    }
    final url = await _api.startGithubLogin(returnTo: returnTo);
    if (url.isEmpty) {
      throw const ApiException('GitHub did not return an authorization URL.');
    }
    _redirect.go(url);
  }

  Future<void> _manageGithub() async {
    String? returnTo;
    final base = Uri.base;
    if (base.scheme == 'http' || base.scheme == 'https') {
      returnTo = base.origin;
    }
    final url = await _api.startGithubInstall(returnTo: returnTo);
    if (url.isEmpty) {
      throw const ApiException('GitHub did not return an installation URL.');
    }
    _redirect.go(url);
  }

  Future<void> _logout() async {
    try {
      await _api.logout();
    } on ApiException {
      // Local session still clears so the UI cannot get stuck.
    }
    _api.clearSessionToken();
    if (!mounted) return;
    _session.value = null;
  }

  bool _isCurrentLocation(String location) {
    final router = _router;
    if (router == null) return false;
    final current = router.routeInformationProvider.value.uri;
    final target = Uri.parse(location);
    return current.path == target.path && current.query == target.query;
  }

  void _go(String location, {Object? extra}) {
    if (_isCurrentLocation(location)) return;
    _router?.go(location, extra: extra);
  }

  void _replace(String location, {Object? extra}) {
    if (_isCurrentLocation(location)) return;
    _router?.replace(location, extra: extra);
  }

  GoRouter _createRouter() {
    return GoRouter(
      initialLocation: AppRoutes.dashboard,
      routes: [
        GoRoute(
          path: AppRoutes.dashboard,
          builder: (context, state) {
            return DashboardScreen(
              api: _api,
              session: _session,
              onRepositorySelected: (repository) {
                _go(
                  AppRoutes.issues(repository.owner, repository.repo),
                  extra: repository,
                );
              },
              onConnectGithub: _connectGithub,
              onManageGithub: _manageGithub,
              onLogout: _logout,
              refreshGrantsOnStart:
                  widget.refreshGrantsOnStart ??
                  Uri.base.queryParameters.containsKey('connected'),
              initialAuthError:
                  widget.initialAuthError ??
                  Uri.base.queryParameters['auth_error'],
            );
          },
        ),
        GoRoute(
          path: '/r/:owner/:repo',
          builder: (context, state) {
            final owner = state.pathParameters['owner'] ?? '';
            final repo = state.pathParameters['repo'] ?? '';
            final repository = state.extra is Repository
                ? state.extra as Repository
                : AppRoutes.repositoryFromPath(owner, repo);

            return IssuesScreen(
              api: _api,
              cache: _cache,
              repository: repository,
              onIssueSelected: (issue, {String? ref}) {
                _go(
                  AppRoutes.repair(
                    owner: owner,
                    repo: repo,
                    number: issue.number,
                    ref: ref,
                  ),
                  extra: RepairNavExtra(repository: repository, issue: issue),
                );
              },
              onBack: () => _go(AppRoutes.dashboard),
            );
          },
        ),
        GoRoute(
          path: '/r/:owner/:repo/issues/:number',
          redirect: (context, state) {
            final owner = state.pathParameters['owner'] ?? '';
            final repo = state.pathParameters['repo'] ?? '';
            final number = int.tryParse(state.pathParameters['number'] ?? '');
            if (number == null) return AppRoutes.dashboard;
            return AppRoutes.repair(
              owner: owner,
              repo: repo,
              number: number,
              ref: state.uri.queryParameters['ref'],
            );
          },
        ),
        GoRoute(
          path: '/r/:owner/:repo/issues/:number/:stage',
          builder: (context, state) {
            final owner = state.pathParameters['owner'] ?? '';
            final repoName = state.pathParameters['repo'] ?? '';
            final number =
                int.tryParse(state.pathParameters['number'] ?? '') ?? 0;
            final ref = state.uri.queryParameters['ref'];
            final requested = AppRoutes.stageFrom(
              state.pathParameters['stage'],
            );

            final extra = state.extra;
            late final Repository repository;
            late final Issue issue;
            if (extra is RepairNavExtra) {
              repository = extra.repository;
              issue = extra.issue;
            } else if (extra is Repository) {
              repository = extra;
              issue = Issue(number: number, title: '');
            } else {
              repository = AppRoutes.repositoryFromPath(owner, repoName);
              issue = Issue(number: number, title: '');
            }

            void commit(RepairStage stage, {required bool replace}) {
              final location = AppRoutes.repair(
                owner: owner,
                repo: repoName,
                number: number,
                stage: stage,
                ref: ref,
              );
              final nav = RepairNavExtra(repository: repository, issue: issue);
              if (replace) {
                _replace(location, extra: nav);
              } else {
                _go(location, extra: nav);
              }
            }

            return RepairSession(
              key: ValueKey('$owner/$repoName/$number/${ref ?? ''}'),
              api: _api,
              cache: _cache,
              repository: repository,
              issue: issue,
              ref: ref,
              redirect: _redirect,
              session: _session,
              onConnectGithub: _connectGithub,
              requestedStage: requested,
              onStageCommitted: (stage) => commit(stage, replace: false),
              onStageNormalized: (stage) => commit(stage, replace: true),
              onBack: () =>
                  _go(AppRoutes.issues(owner, repoName), extra: repository),
            );
          },
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!_authReady) {
      return MaterialApp(
        title: 'PatchPilot',
        debugShowCheckedModeBanner: false,
        theme: AppTheme.build(),
        home: const Scaffold(
          body: Center(
            child: SizedBox(
              width: 22,
              height: 22,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
          ),
        ),
      );
    }

    _router ??= _createRouter();

    return MaterialApp.router(
      title: 'PatchPilot',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.build(),
      routerConfig: _router,
    );
  }
}

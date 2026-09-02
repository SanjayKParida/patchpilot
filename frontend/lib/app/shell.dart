import 'package:flutter/material.dart';

import 'package:patchpilot_web/features/dashboard/screens/dashboard_screen.dart';
import 'package:patchpilot_web/features/repair/diagnosis/screens/diagnosis_screen.dart';
import 'package:patchpilot_web/features/repositories/screens/issues_screen.dart';
import 'package:patchpilot_web/models/models.dart';
import 'package:patchpilot_web/services/analysis_cache.dart';
import 'package:patchpilot_web/services/api_client.dart';
import 'package:patchpilot_web/services/browser_location.dart';
import 'package:patchpilot_web/services/github_redirect.dart';
import 'package:patchpilot_web/services/session_token.dart';

/// Navigation for the whole product.
///
/// Dashboard -> Issues -> Diagnosis, with back at every step. A
/// Navigator stack is all this needs; the only shared state is the
/// current repository, issue, and PatchPilot session.
///
/// Repair/shell will later host the shared Issue → Diagnosis →
/// Context → Patch → Validation → Review → Pull Request workspace.
/// Until that exists, diagnosis is still pushed as its own route.
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
  final _navigatorKey = GlobalKey<NavigatorState>();

  Repository? _repository;
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

  void _openIssues(Repository repository) {
    setState(() => _repository = repository);

    _navigatorKey.currentState?.push(
      MaterialPageRoute<void>(
        builder: (_) => IssuesScreen(
          api: _api,
          repository: repository,
          onIssueSelected: _openDiagnosis,
          onBack: () => _navigatorKey.currentState?.pop(),
        ),
      ),
    );
  }

  void _openDiagnosis(Issue issue, {String? ref}) {
    final repository = _repository;
    if (repository == null) return;

    _navigatorKey.currentState?.push(
      MaterialPageRoute<void>(
        builder: (_) => DiagnosisScreen(
          api: _api,
          cache: _cache,
          repository: repository,
          issue: issue,
          ref: ref,
          onBack: () => _navigatorKey.currentState?.pop(),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!_authReady) {
      return const Scaffold(
        body: Center(
          child: SizedBox(
            width: 22,
            height: 22,
            child: CircularProgressIndicator(strokeWidth: 2),
          ),
        ),
      );
    }

    return Navigator(
      key: _navigatorKey,
      onGenerateRoute: (_) => MaterialPageRoute<void>(
        builder: (_) => DashboardScreen(
          api: _api,
          session: _session,
          onRepositorySelected: _openIssues,
          onConnectGithub: _connectGithub,
          onManageGithub: _manageGithub,
          onLogout: _logout,
          refreshGrantsOnStart:
              widget.refreshGrantsOnStart ??
              Uri.base.queryParameters.containsKey('connected'),
          initialAuthError:
              widget.initialAuthError ?? Uri.base.queryParameters['auth_error'],
        ),
      ),
    );
  }
}

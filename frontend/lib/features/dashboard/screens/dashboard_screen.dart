import 'dart:async';

import 'package:flutter/material.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/core/widgets/app_background.dart';
import 'package:patchpilot_web/core/widgets/common.dart';
import 'package:patchpilot_web/models/models.dart';
import 'package:patchpilot_web/services/api_client.dart';

import '../widgets/dashboard_cards.dart';

/// Landing: developer workspace / repository launcher.
class DashboardScreen extends StatefulWidget {
  final ApiClient api;
  final ValueNotifier<AuthUser?> session;
  final Future<void> Function() onConnectGithub;
  final Future<void> Function() onManageGithub;
  final Future<void> Function() onLogout;
  final void Function(Repository) onRepositorySelected;
  final bool refreshGrantsOnStart;
  final String? initialAuthError;

  const DashboardScreen({
    super.key,
    required this.api,
    required this.session,
    required this.onRepositorySelected,
    required this.onConnectGithub,
    required this.onManageGithub,
    required this.onLogout,
    this.refreshGrantsOnStart = false,
    this.initialAuthError,
  });

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  final _searchController = TextEditingController();

  Repository? _demo;
  List<Repository> _repos = const [];
  bool _loadingDemo = true;
  bool _loadingRepos = false;
  bool _connecting = false;
  String? _error;
  String _query = '';
  bool _managing = false;
  bool _grantRefreshStarted = false;

  AuthUser? get _user => widget.session.value;

  @override
  void initState() {
    super.initState();
    widget.session.addListener(_onSession);
    _error = widget.initialAuthError;
    _loadDemo();

    if (_user != null) {
      _loadRepos(refreshInBackground: true);
    }
  }

  @override
  void dispose() {
    widget.session.removeListener(_onSession);
    _searchController.dispose();
    super.dispose();
  }

  void _onSession() {
    if (_user != null) {
      _loadRepos(refreshInBackground: true);
    } else {
      _grantRefreshStarted = false;
      setState(() => _repos = const []);
    }
    setState(() {});
  }

  Future<void> _loadDemo() async {
    setState(() => _loadingDemo = true);

    try {
      final demo = await widget.api.getDemoRepository();

      if (!mounted) return;

      setState(() => _demo = demo);
    } on ApiException catch (e) {
      if (!mounted) return;

      setState(() => _error = e.message);
    } finally {
      if (mounted) {
        setState(() => _loadingDemo = false);
      }
    }
  }

  Future<void> _loadRepos({bool refreshInBackground = false}) async {
    setState(() => _loadingRepos = true);

    try {
      final repos = await widget.api.listAuthorizedRepositories();
      if (!mounted) return;
      setState(() => _repos = repos);
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loadingRepos = false);
    }

    if (!mounted || !refreshInBackground) return;
    unawaited(_refreshGrantsInBackground());
  }

  Future<void> _refreshGrantsInBackground() async {
    if (_grantRefreshStarted) return;
    _grantRefreshStarted = true;

    try {
      final repos = await widget.api.refreshAuthorizedRepositories();
      if (!mounted) return;
      setState(() => _repos = repos);
    } on ApiException {
      // Keep the cached list. A failed GitHub refresh is not a dashboard error.
    }
  }

  Future<void> _connect() async {
    setState(() {
      _connecting = true;
      _error = null;
    });

    try {
      await widget.onConnectGithub();
    } on ApiException catch (e) {
      if (!mounted) return;

      setState(() => _error = e.message);
    } finally {
      if (mounted) {
        setState(() => _connecting = false);
      }
    }
  }

  Future<void> _manage() async {
    setState(() {
      _managing = true;
      _error = null;
    });

    try {
      await widget.onManageGithub();
    } on ApiException catch (e) {
      if (!mounted) return;

      setState(() => _error = e.message);
    } finally {
      if (mounted) {
        setState(() => _managing = false);
      }
    }
  }

  List<Repository> get _visibleRepos {
    final term = _query.trim().toLowerCase();

    if (term.isEmpty) return _repos;

    return _repos.where((repo) {
      return repo.fullName.toLowerCase().contains(term) ||
          (repo.description ?? '').toLowerCase().contains(term);
    }).toList();
  }

  bool get _showManageBelowList =>
      _user != null && (_loadingRepos || _repos.isNotEmpty);

  @override
  Widget build(BuildContext context) {
    final user = _user;

    return Scaffold(
      backgroundColor: Colors.transparent,
      body: AppBackground(
        child: PageBody(
          padding: const EdgeInsets.fromLTRB(32, 28, 32, 48),
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 900),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  _buildTopBar(user),
                  const SizedBox(height: 32),
                  _buildHeading(),
                  const SizedBox(height: 24),
                  if (_error != null) ...[
                    ErrorNotice(message: _error!),
                    const SizedBox(height: 6),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: TextButton(
                        style: TextButton.styleFrom(
                          foregroundColor: AppTheme.textMuted,
                          padding: EdgeInsets.zero,
                        ),
                        onPressed: user == null ? _connect : _manage,
                        child: Text(
                          user == null ? 'Try again' : 'Reconnect GitHub',
                        ),
                      ),
                    ),
                    const SizedBox(height: 18),
                  ],
                  _buildRepositoryWorkspace(user),
                  const SizedBox(height: 42),
                  _buildDemoSection(),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildRepositoryWorkspace(AuthUser? user) {
    return Container(
      decoration: BoxDecoration(
        color: AppTheme.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppTheme.borderSubtle),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 18, 20, 16),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                const Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'YOUR REPOSITORIES',
                        style: TextStyle(
                          fontSize: 10,
                          fontWeight: FontWeight.w700,
                          letterSpacing: 1.1,
                          color: AppTheme.textMuted,
                        ),
                      ),
                      SizedBox(height: 5),
                      Text(
                        'Choose a repository',
                        style: TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                ),
                if (user != null && !_loadingRepos && _repos.isNotEmpty)
                  Text(
                    '${_repos.length} connected',
                    style: const TextStyle(
                      fontSize: 11,
                      fontFamily: AppTheme.mono,
                      color: AppTheme.textMuted,
                    ),
                  ),
              ],
            ),
          ),
          Container(height: 1, color: AppTheme.borderSubtle),
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 4),
            child: user == null
                ? ConnectPrompt(connecting: _connecting, onConnect: _connect)
                : AuthorizedWorkspace(
                    loading: _loadingRepos,
                    managing: _managing,
                    controller: _searchController,
                    hasAnyRepositories: _repos.isNotEmpty,
                    repositories: _visibleRepos,
                    totalCount: _repos.length,
                    query: _query,
                    onQuery: (value) => setState(() => _query = value),
                    onOpen: widget.onRepositorySelected,
                    onManage: _manage,
                  ),
          ),
          if (_showManageBelowList)
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 12),
              child: Align(
                alignment: Alignment.centerRight,
                child: TextButton(
                  style: TextButton.styleFrom(
                    foregroundColor: AppTheme.textMuted,
                    padding: const EdgeInsets.symmetric(horizontal: 8),
                  ),
                  onPressed: _managing ? null : _manage,
                  child: const Text(
                    'Manage GitHub access',
                    style: TextStyle(fontSize: 11.5),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildHeading() {
    final user = _user;

    late final String eyebrow;
    late final String headline;
    late final String subtext;

    if (user == null) {
      eyebrow = 'GET STARTED';
      headline = 'Bring your code into PatchPilot';
      subtext =
          'Connect GitHub to diagnose issues, generate fixes, and open pull requests.';
    } else if (_repos.isEmpty && _loadingRepos) {
      eyebrow = 'WORKSPACE';
      headline = 'Loading your repositories';
      subtext = 'Fetching the repositories available to PatchPilot…';
    } else if (_repos.isEmpty) {
      eyebrow = 'WORKSPACE';
      headline = 'No repositories connected';
      subtext = 'Choose which repositories PatchPilot can access from GitHub.';
    } else {
      eyebrow = 'WORKSPACE';
      headline = 'Start with a repository';
      subtext = _repos.length == 1
          ? '1 repository is ready for issue triage.'
          : '${_repos.length} repositories are ready for issue triage.';
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          eyebrow,
          style: const TextStyle(
            fontSize: 10,
            fontWeight: FontWeight.w700,
            letterSpacing: 1.2,
            color: AppTheme.accent,
          ),
        ),
        const SizedBox(height: 9),
        Text(
          headline,
          style: AppTypography.title.copyWith(
            fontSize: 30,
            fontWeight: FontWeight.w700,
            letterSpacing: -0.7,
            height: 1.08,
          ),
        ),
        const SizedBox(height: 8),
        ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 650),
          child: Text(
            subtext,
            style: const TextStyle(
              fontSize: 13.5,
              color: AppTheme.textMuted,
              height: 1.5,
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildDemoSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            const Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'NO GITHUB REQUIRED',
                    style: TextStyle(
                      fontSize: 10,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 1.1,
                      color: AppTheme.textMuted,
                    ),
                  ),
                  SizedBox(height: 5),
                  Text(
                    'Try the workflow',
                    style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
                  ),
                ],
              ),
            ),
            const Text(
              'DEMO',
              style: TextStyle(
                fontSize: 10,
                fontFamily: AppTheme.mono,
                fontWeight: FontWeight.w700,
                letterSpacing: 0.8,
                color: AppTheme.textMuted,
              ),
            ),
          ],
        ),
        const SizedBox(height: 10),
        Container(
          decoration: BoxDecoration(
            color: AppTheme.surfaceAlt,
            borderRadius: BorderRadius.circular(9),
            border: Border.all(color: AppTheme.borderSubtle),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: _loadingDemo
              ? const DemoRowSkeleton()
              : _demo != null
              ? DemoRow(
                  repository: _demo!,
                  onOpen: () => widget.onRepositorySelected(_demo!),
                )
              : const SizedBox.shrink(),
        ),
      ],
    );
  }

  Widget _buildTopBar(AuthUser? user) {
    return Row(
      children: [
        const Branding(size: 24),
        const SizedBox(width: 10),
        Container(
          width: 4,
          height: 4,
          decoration: const BoxDecoration(
            color: AppTheme.textMuted,
            shape: BoxShape.circle,
          ),
        ),
        const SizedBox(width: 8),
        const Text(
          'Workspace',
          style: TextStyle(fontSize: 11.5, color: AppTheme.textMuted),
        ),
        const Spacer(),
        if (user != null) ...[
          UserChip(user: user),
          Container(
            width: 1,
            height: 16,
            margin: const EdgeInsets.symmetric(horizontal: 14),
            color: AppTheme.borderSubtle,
          ),
          TextButton(
            style: TextButton.styleFrom(
              foregroundColor: AppTheme.danger,
              backgroundColor: AppTheme.danger.withValues(alpha: 0.10),
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
              minimumSize: const Size(0, 32),
              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
              shape: RoundedRectangleBorder(
                borderRadius: AppRadii.button,
                side: BorderSide(
                  color: AppTheme.danger.withValues(alpha: 0.45),
                ),
              ),
            ),
            onPressed: widget.onLogout,
            child: const Text(
              'Log out',
              style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
            ),
          ),
        ],
      ],
    );
  }
}

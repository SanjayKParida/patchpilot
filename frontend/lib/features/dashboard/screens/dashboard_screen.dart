import 'package:flutter/material.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/core/widgets/common.dart';
import 'package:patchpilot_web/models/models.dart';
import 'package:patchpilot_web/services/api_client.dart';

import '../widgets/dashboard_cards.dart';

/// Landing: demo first, then the user's authorized GitHub repositories.
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

  AuthUser? get _user => widget.session.value;

  @override
  void initState() {
    super.initState();
    widget.session.addListener(_onSession);
    _error = widget.initialAuthError;
    _loadDemo();
    if (_user != null) {
      _loadRepos(refresh: widget.refreshGrantsOnStart);
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
      _loadRepos();
    } else {
      setState(() => _repos = const []);
    }
    setState(() {});
  }

  Future<void> _loadDemo() async {
    setState(() {
      _loadingDemo = true;
    });
    try {
      final demo = await widget.api.getDemoRepository();
      if (!mounted) return;
      setState(() => _demo = demo);
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loadingDemo = false);
    }
  }

  Future<void> _loadRepos({bool refresh = false}) async {
    setState(() => _loadingRepos = true);
    try {
      final repos = refresh
          ? await widget.api.refreshAuthorizedRepositories()
          : await widget.api.listAuthorizedRepositories();
      if (!mounted) return;
      setState(() => _repos = repos);
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loadingRepos = false);
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
      if (mounted) setState(() => _connecting = false);
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
      if (mounted) setState(() => _managing = false);
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

  @override
  Widget build(BuildContext context) {
    final user = _user;

    return Scaffold(
      body: PageBody(
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 48),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _buildTopBar(user),
            const SizedBox(height: 36),
            const Text(
              'Open the demo immediately, or connect GitHub to work on '
              'repositories you have authorized.',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 16,
                color: AppTheme.textMuted,
                height: 1.6,
              ),
            ),
            if (_error != null) ...[
              const SizedBox(height: 20),
              ErrorNotice(message: _error!),
              const SizedBox(height: 12),
              Center(
                child: TextButton(
                  onPressed: user == null ? _connect : _manage,
                  child: Text(user == null ? 'Try again' : 'Reconnect GitHub'),
                ),
              ),
            ],
            const SizedBox(height: 36),
            const SectionTitle('Demo'),
            const SizedBox(height: 12),
            if (_loadingDemo)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 24),
                child: Center(child: CircularProgressIndicator()),
              )
            else if (_demo != null)
              DemoCard(
                repository: _demo!,
                onOpen: () => widget.onRepositorySelected(_demo!),
              ),
            const SizedBox(height: 36),
            SectionTitle(user == null ? 'Your GitHub' : 'Your repositories'),
            const SizedBox(height: 12),
            if (user == null)
              ConnectCard(connecting: _connecting, onConnect: _connect)
            else
              AuthorizedList(
                loading: _loadingRepos,
                managing: _managing,
                controller: _searchController,
                repositories: _visibleRepos,
                onQuery: (value) => setState(() => _query = value),
                onOpen: widget.onRepositorySelected,
                onManage: _manage,
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildTopBar(AuthUser? user) {
    return Row(
      children: [
        const Branding(size: 36),
        const Spacer(),
        if (user != null) ...[
          UserChip(user: user),
          const SizedBox(width: 12),
          TextButton(onPressed: widget.onLogout, child: const Text('Log out')),
        ],
      ],
    );
  }
}

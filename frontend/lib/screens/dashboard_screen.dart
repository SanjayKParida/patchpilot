import 'package:flutter/material.dart';

import '../models/models.dart';
import '../services/api_client.dart';
import '../theme.dart';
import '../widgets/common.dart';

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
              _DemoCard(
                repository: _demo!,
                onOpen: () => widget.onRepositorySelected(_demo!),
              ),
            const SizedBox(height: 36),
            SectionTitle(
              user == null ? 'Your GitHub' : 'Your repositories',
            ),
            const SizedBox(height: 12),
            if (user == null)
              _ConnectCard(
                connecting: _connecting,
                onConnect: _connect,
              )
            else
              _AuthorizedList(
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
          _UserChip(user: user),
          const SizedBox(width: 12),
          TextButton(
            onPressed: widget.onLogout,
            child: const Text('Log out'),
          ),
        ],
      ],
    );
  }
}

class _UserChip extends StatelessWidget {
  final AuthUser user;

  const _UserChip({required this.user});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        if (user.avatarUrl.isNotEmpty)
          CircleAvatar(
            radius: 12,
            backgroundImage: NetworkImage(user.avatarUrl),
          )
        else
          const CircleAvatar(
            radius: 12,
            backgroundColor: AppTheme.surfaceAlt,
            child: Icon(Icons.person_outline, size: 14),
          ),
        const SizedBox(width: 8),
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              user.githubLogin,
              style: const TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w600,
              ),
            ),
            const Text(
              'Connected',
              style: TextStyle(fontSize: 11, color: AppTheme.success),
            ),
          ],
        ),
      ],
    );
  }
}

class _DemoCard extends StatelessWidget {
  final Repository repository;
  final VoidCallback onOpen;

  const _DemoCard({required this.repository, required this.onOpen});

  @override
  Widget build(BuildContext context) {
    return Panel(
      background: const Color(0xFF141A28),
      borderColor: AppTheme.accent.withValues(alpha: 0.45),
      padding: const EdgeInsets.all(24),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 8,
                        vertical: 3,
                      ),
                      decoration: BoxDecoration(
                        color: AppTheme.accent.withValues(alpha: 0.16),
                        borderRadius: BorderRadius.circular(999),
                      ),
                      child: const Text(
                        'Demo',
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                          letterSpacing: 0.4,
                          color: AppTheme.accent,
                        ),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Flexible(
                      child: Text(
                        repository.fullName,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Text(
                  repository.description ??
                      'Try PatchPilot on prepared issues',
                  style: const TextStyle(
                    fontSize: 13.5,
                    height: 1.5,
                    color: AppTheme.textMuted,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 16),
          FilledButton(
            onPressed: onOpen,
            child: const Text('Open Demo'),
          ),
        ],
      ),
    );
  }
}

class _ConnectCard extends StatelessWidget {
  final bool connecting;
  final VoidCallback onConnect;

  const _ConnectCard({required this.connecting, required this.onConnect});

  @override
  Widget build(BuildContext context) {
    return Panel(
      padding: const EdgeInsets.all(24),
      child: Row(
        children: [
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Connect GitHub',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
                ),
                SizedBox(height: 6),
                Text(
                  'Authorize PatchPilot and choose the repositories it may use.',
                  style: TextStyle(
                    fontSize: 13.5,
                    height: 1.5,
                    color: AppTheme.textMuted,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 16),
          FilledButton(
            onPressed: connecting ? null : onConnect,
            child: connecting
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: Colors.white,
                    ),
                  )
                : const Text('Connect GitHub'),
          ),
        ],
      ),
    );
  }
}

class _AuthorizedList extends StatelessWidget {
  final bool loading;
  final bool managing;
  final TextEditingController controller;
  final List<Repository> repositories;
  final ValueChanged<String> onQuery;
  final void Function(Repository) onOpen;
  final VoidCallback onManage;

  const _AuthorizedList({
    required this.loading,
    required this.managing,
    required this.controller,
    required this.repositories,
    required this.onQuery,
    required this.onOpen,
    required this.onManage,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (!loading && repositories.isEmpty)
          _SelectRepositoriesCard(
            managing: managing,
            onSelect: onManage,
          )
        else
          Panel(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
            child: Column(
              children: [
                TextField(
                  controller: controller,
                  onChanged: onQuery,
                  decoration: const InputDecoration(
                    hintText: 'Search repositories...',
                    prefixIcon: Icon(Icons.search, color: AppTheme.textMuted),
                  ),
                ),
                const SizedBox(height: 12),
                if (loading)
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 32),
                    child: Center(child: CircularProgressIndicator()),
                  )
                else
                  ...repositories.map(
                    (repo) => _RepoRow(
                      repository: repo,
                      onOpen: () => onOpen(repo),
                    ),
                  ),
              ],
            ),
          ),
        if (!loading && repositories.isNotEmpty) ...[
          const SizedBox(height: 8),
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton(
              onPressed: managing ? null : onManage,
              child: const Text('Manage GitHub access'),
            ),
          ),
        ],
      ],
    );
  }
}

class _SelectRepositoriesCard extends StatelessWidget {
  final bool managing;
  final VoidCallback onSelect;

  const _SelectRepositoriesCard({
    required this.managing,
    required this.onSelect,
  });

  @override
  Widget build(BuildContext context) {
    return Panel(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Connect a repository',
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 6),
          const Text(
            'Choose the repositories PatchPilot can access.',
            style: TextStyle(
              fontSize: 13.5,
              height: 1.5,
              color: AppTheme.textMuted,
            ),
          ),
          const SizedBox(height: 16),
          FilledButton(
            onPressed: managing ? null : onSelect,
            child: managing
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: Colors.white,
                    ),
                  )
                : const Text('Select repositories on GitHub'),
          ),
        ],
      ),
    );
  }
}

class _RepoRow extends StatelessWidget {
  final Repository repository;
  final VoidCallback onOpen;

  const _RepoRow({required this.repository, required this.onOpen});

  @override
  Widget build(BuildContext context) {
    final visibility = repository.private ? 'Private' : 'Public';
    final access = repository.canWrite == true
        ? 'Write'
        : repository.canRead == false
            ? 'No access'
            : 'Read';

    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: repository.canRead == false ? null : onOpen,
          borderRadius: BorderRadius.circular(10),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 12),
            child: Row(
              children: [
                Icon(
                  repository.private
                      ? Icons.lock_outline
                      : Icons.folder_outlined,
                  size: 18,
                  color: AppTheme.textMuted,
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    repository.fullName,
                    style: const TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
                Text(
                  visibility,
                  style: const TextStyle(
                    fontSize: 12,
                    color: AppTheme.textMuted,
                  ),
                ),
                const SizedBox(width: 12),
                Text(
                  access,
                  style: TextStyle(
                    fontSize: 12,
                    color: repository.canWrite == true
                        ? AppTheme.success
                        : AppTheme.textMuted,
                  ),
                ),
                const SizedBox(width: 8),
                const Icon(
                  Icons.chevron_right,
                  size: 18,
                  color: AppTheme.textMuted,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

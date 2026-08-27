import 'package:flutter/material.dart';

import '../models/models.dart';
import '../services/api_client.dart';
import '../services/recent_repositories.dart';
import '../theme.dart';
import '../widgets/common.dart';

/// Landing screen: get the user into an analysis in one action.
class DashboardScreen extends StatefulWidget {
  final ApiClient api;
  final void Function(Repository) onRepositorySelected;

  const DashboardScreen({
    super.key,
    required this.api,
    required this.onRepositorySelected,
  });

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  final _controller = TextEditingController();
  final _recentStore = RecentRepositories();

  List<Repository> _recent = const [];
  bool _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _recent = _recentStore.load();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _analyze([String? url]) async {
    final target = (url ?? _controller.text).trim();

    if (target.isEmpty) {
      setState(() => _error = 'Enter a GitHub repository URL.');
      return;
    }

    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final repository = await widget.api.resolveRepository(target);
      final updated = _recentStore.add(repository);

      if (!mounted) return;
      setState(() => _recent = updated);

      widget.onRepositorySelected(repository);
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: PageBody(
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 64),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Center(child: Branding(size: 40)),
            const SizedBox(height: 16),
            const Text(
              'Point PatchPilot at a repository, pick an issue, and get a '
              'diagnosis grounded in the code.',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 16,
                color: AppTheme.textMuted,
                height: 1.6,
              ),
            ),
            const SizedBox(height: 48),
            _buildInput(),
            if (_error != null) ...[
              const SizedBox(height: 16),
              ErrorNotice(message: _error!),
            ],
            if (_recent.isNotEmpty) ...[
              const SizedBox(height: 48),
              const SectionTitle('Recent repositories'),
              ..._recent.map(_buildRecentRow),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildInput() {
    return Panel(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text(
            'Repository URL',
            style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 12),
          LayoutBuilder(
            builder: (context, constraints) {
              final field = TextField(
                controller: _controller,
                enabled: !_loading,
                autofocus: true,
                onSubmitted: (_) => _analyze(),
                style: const TextStyle(fontSize: 15),
                decoration: const InputDecoration(
                  hintText: 'https://github.com/owner/repo',
                  prefixIcon: Icon(Icons.link, color: AppTheme.textMuted),
                ),
              );

              final button = FilledButton(
                onPressed: _loading ? null : () => _analyze(),
                child: _loading
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      )
                    : const Text('Analyze repository'),
              );

              // Stack on narrow viewports so neither control is cramped.
              if (constraints.maxWidth < 520) {
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [field, const SizedBox(height: 12), button],
                );
              }

              return Row(
                children: [
                  Expanded(child: field),
                  const SizedBox(width: 12),
                  button,
                ],
              );
            },
          ),
        ],
      ),
    );
  }

  Widget _buildRecentRow(Repository repository) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: _loading ? null : () => _analyze(repository.fullName),
          borderRadius: BorderRadius.circular(10),
          child: Panel(
            padding: const EdgeInsets.symmetric(
              horizontal: 20,
              vertical: 16,
            ),
            child: Row(
              children: [
                const Icon(
                  Icons.folder_outlined,
                  size: 18,
                  color: AppTheme.textMuted,
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        repository.fullName,
                        style: const TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      if (repository.description != null &&
                          repository.description!.isNotEmpty) ...[
                        const SizedBox(height: 4),
                        Text(
                          repository.description!,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontSize: 13,
                            color: AppTheme.textMuted,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
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

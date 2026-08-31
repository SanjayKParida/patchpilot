import 'dart:async';

import 'package:flutter/material.dart';

import '../models/models.dart';
import '../services/api_client.dart';
import '../theme.dart';
import '../widgets/common.dart';

/// Issue list for a repository: the user chooses what to investigate.
class IssuesScreen extends StatefulWidget {
  final ApiClient api;
  final Repository repository;
  final void Function(Issue issue, {String? ref}) onIssueSelected;
  final VoidCallback onBack;

  const IssuesScreen({
    super.key,
    required this.api,
    required this.repository,
    required this.onIssueSelected,
    required this.onBack,
  });

  @override
  State<IssuesScreen> createState() => _IssuesScreenState();
}

class _IssuesScreenState extends State<IssuesScreen> {
  final _searchController = TextEditingController();
  final _refController = TextEditingController();

  List<Issue> _issues = const [];
  bool _loading = true;
  String? _error;
  String _query = '';
  String _snapshotStatus = 'preparing';
  String? _snapshotSha;
  int _snapshotFileCount = 0;
  String? _snapshotError;
  int _snapshotPercent = 0;
  Timer? _progressTimer;

  @override
  void initState() {
    super.initState();
    _load();
    _prepareSnapshot();
  }

  @override
  void dispose() {
    _progressTimer?.cancel();
    _searchController.dispose();
    _refController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final issues = await widget.api.listIssues(
        widget.repository.owner,
        widget.repository.repo,
      );

      if (!mounted) return;
      setState(() => _issues = issues);
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _prepareSnapshot() async {
    _startProgressPoll();
    try {
      final snapshot = await widget.api.prepareRepositorySnapshot(
        widget.repository.owner,
        widget.repository.repo,
      );
      if (!mounted) return;
      setState(() {
        _snapshotStatus = snapshot.status;
        _snapshotSha = snapshot.commitSha;
        _snapshotFileCount = snapshot.fileCount;
        _snapshotPercent = snapshot.isReady ? 100 : snapshot.progressPercent;
        _snapshotError = null;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _snapshotStatus = 'failed';
        _snapshotError = e.message;
      });
    } finally {
      _progressTimer?.cancel();
    }
  }

  void _startProgressPoll() {
    _progressTimer?.cancel();
    _progressTimer = Timer.periodic(const Duration(milliseconds: 400), (_) {
      _tickSnapshotProgress();
    });
    _tickSnapshotProgress();
  }

  Future<void> _tickSnapshotProgress() async {
    try {
      final snapshot = await widget.api.getRepositorySnapshot(
        widget.repository.owner,
        widget.repository.repo,
      );
      if (!mounted) return;
      if (_snapshotStatus == 'ready' || _snapshotStatus == 'failed') return;
      setState(() {
        _snapshotPercent = snapshot.progressPercent;
        if (snapshot.filesTotal > 0) {
          _snapshotFileCount = snapshot.fileCount;
        }
      });
    } on ApiException {
      // Progress is best-effort; POST still owns success or failure.
    }
  }

  /// Filtering is local: the list is small and the user gets instant
  /// feedback without a request per keystroke.
  List<Issue> get _visible {
    final term = _query.trim().toLowerCase();
    if (term.isEmpty) return _issues;

    return _issues.where((issue) {
      return issue.title.toLowerCase().contains(term) ||
          issue.body.toLowerCase().contains(term) ||
          '#${issue.number}'.contains(term);
    }).toList();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: PageBody(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _buildHeader(),
            const SizedBox(height: 12),
            _buildSnapshotStatus(),
            const SizedBox(height: 24),
            TextField(
              controller: _searchController,
              onChanged: (value) => setState(() => _query = value),
              decoration: const InputDecoration(
                hintText: 'Filter by number, title or description',
                prefixIcon: Icon(Icons.search, color: AppTheme.textMuted),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _refController,
              style: const TextStyle(
                fontFamily: AppTheme.mono,
                fontSize: 13.5,
              ),
              decoration: const InputDecoration(
                hintText:
                    'Commit SHA or ref (optional). Leave blank for current HEAD.',
                prefixIcon: Icon(Icons.commit, color: AppTheme.textMuted),
              ),
            ),
            const SizedBox(height: 24),
            if (_loading)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 64),
                child: Center(child: CircularProgressIndicator()),
              )
            else if (_error != null)
              ErrorNotice(message: _error!, onRetry: _load)
            else if (_visible.isEmpty)
              EmptyNotice(
                icon: _issues.isEmpty
                    ? Icons.inbox_outlined
                    : Icons.search_off,
                message: _issues.isEmpty
                    ? 'This repository has no open issues.'
                    : 'No issues match "$_query".',
              )
            else ...[
              SectionTitle(
                'Issues',
                trailing: '${_visible.length} of ${_issues.length}',
              ),
              ..._visible.map(_buildIssueRow),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildHeader() {
    return Row(
      children: [
        IconButton(
          onPressed: widget.onBack,
          icon: const Icon(Icons.arrow_back),
          tooltip: 'Back to repositories',
          color: AppTheme.textMuted,
        ),
        const SizedBox(width: 8),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                widget.repository.fullName,
                style: const TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.w700,
                  letterSpacing: -0.3,
                ),
              ),
              if (widget.repository.description != null &&
                  widget.repository.description!.isNotEmpty) ...[
                const SizedBox(height: 4),
                Text(
                  widget.repository.description!,
                  style: const TextStyle(
                    fontSize: 14,
                    color: AppTheme.textMuted,
                  ),
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildSnapshotStatus() {
    late final IconData icon;
    late final Color color;
    late final String label;

    if (_snapshotStatus == 'ready') {
      icon = Icons.check_circle_outline;
      color = AppTheme.success;
      final shortSha = (_snapshotSha ?? '').isEmpty
          ? ''
          : (_snapshotSha!.length >= 7
              ? _snapshotSha!.substring(0, 7)
              : _snapshotSha!);
      label = shortSha.isEmpty
          ? 'Repository ready'
          : 'Repository ready at $shortSha · $_snapshotFileCount files';
    } else if (_snapshotStatus == 'failed') {
      icon = Icons.error_outline;
      color = AppTheme.danger;
      label = _snapshotError == null || _snapshotError!.isEmpty
          ? 'Could not prepare the repository'
          : 'Could not prepare the repository: $_snapshotError';
    } else {
      icon = Icons.hourglass_empty;
      color = AppTheme.textMuted;
      final percent = _snapshotPercent.clamp(0, 100);
      label = percent > 0
          ? 'Preparing repository… $percent%'
          : 'Preparing repository…';
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Icon(icon, size: 16, color: color),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                label,
                style: TextStyle(fontSize: 13, color: color),
              ),
            ),
          ],
        ),
        if (_snapshotStatus == 'preparing') ...[
          const SizedBox(height: 8),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: _snapshotPercent <= 0
                  ? null
                  : (_snapshotPercent.clamp(0, 100) / 100),
              minHeight: 6,
              color: AppTheme.accent,
              backgroundColor: AppTheme.border,
            ),
          ),
        ],
      ],
    );
  }

  Widget _buildIssueRow(Issue issue) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Panel(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      StatusChip(
                        label: issue.isOpen ? 'Open' : 'Closed',
                        color: issue.isOpen
                            ? AppTheme.success
                            : AppTheme.purple,
                        icon: issue.isOpen
                            ? Icons.error_outline
                            : Icons.check_circle_outline,
                      ),
                      const SizedBox(width: 10),
                      Text(
                        '#${issue.number}',
                        style: const TextStyle(
                          fontSize: 13,
                          fontFamily: AppTheme.mono,
                          color: AppTheme.textMuted,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Text(
                    issue.title,
                    style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w600,
                      height: 1.4,
                    ),
                  ),
                  if (issue.snippet.isNotEmpty) ...[
                    const SizedBox(height: 6),
                    Text(
                      issue.snippet,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 13,
                        color: AppTheme.textMuted,
                        height: 1.5,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(width: 20),
            FilledButton(
              onPressed: _snapshotStatus == 'preparing'
                  ? null
                  : () => widget.onIssueSelected(
                        issue,
                        ref: _refController.text.trim().isEmpty
                            ? null
                            : _refController.text.trim(),
                      ),
              style: FilledButton.styleFrom(
                padding: const EdgeInsets.symmetric(
                  horizontal: 18,
                  vertical: 14,
                ),
              ),
              child: const Text('Analyze'),
            ),
          ],
        ),
      ),
    );
  }
}

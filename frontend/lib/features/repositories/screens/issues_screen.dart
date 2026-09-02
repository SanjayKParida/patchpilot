import 'dart:async';

import 'package:flutter/material.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/core/widgets/common.dart';
import 'package:patchpilot_web/models/models.dart';
import 'package:patchpilot_web/services/api_client.dart';

import '../widgets/issue_row.dart';
import '../widgets/repository_header.dart';
import '../widgets/snapshot_status.dart';

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
            RepositoryHeader(
              repository: widget.repository,
              onBack: widget.onBack,
            ),
            const SizedBox(height: 12),
            SnapshotStatus(
              status: _snapshotStatus,
              sha: _snapshotSha,
              fileCount: _snapshotFileCount,
              error: _snapshotError,
              percent: _snapshotPercent,
            ),
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
              style: const TextStyle(fontFamily: AppTheme.mono, fontSize: 13.5),
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
                icon: _issues.isEmpty ? Icons.inbox_outlined : Icons.search_off,
                message: _issues.isEmpty
                    ? 'This repository has no open issues.'
                    : 'No issues match "$_query".',
              )
            else ...[
              SectionTitle(
                'Issues',
                trailing: '${_visible.length} of ${_issues.length}',
              ),
              ..._visible.map(
                (issue) => IssueRow(
                  issue: issue,
                  analyzeEnabled: _snapshotStatus != 'preparing',
                  onAnalyze: () => widget.onIssueSelected(
                    issue,
                    ref: _refController.text.trim().isEmpty
                        ? null
                        : _refController.text.trim(),
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

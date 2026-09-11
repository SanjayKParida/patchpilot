import 'dart:async';

import 'package:flutter/material.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/core/widgets/app_background.dart';
import 'package:patchpilot_web/core/widgets/common.dart';
import 'package:patchpilot_web/core/widgets/motion.dart';
import 'package:patchpilot_web/models/models.dart';
import 'package:patchpilot_web/services/analysis_cache.dart';
import 'package:patchpilot_web/services/api_client.dart';

import '../widgets/issue_row.dart';
import '../widgets/repository_header.dart';
import '../widgets/snapshot_status.dart';

/// Issue list for a repository: the user chooses what to investigate.
class IssuesScreen extends StatefulWidget {
  final ApiClient api;
  final AnalysisCache cache;
  final Repository repository;
  final void Function(Issue issue, {String? ref}) onIssueSelected;
  final VoidCallback onBack;

  const IssuesScreen({
    super.key,
    required this.api,
    required this.cache,
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

  List<Issue> get _visible {
    final term = _query.trim().toLowerCase();
    if (term.isEmpty) return _issues;

    return _issues.where((issue) {
      return issue.title.toLowerCase().contains(term) ||
          issue.body.toLowerCase().contains(term) ||
          '#${issue.number}'.contains(term);
    }).toList();
  }

  bool _hasCompletedAnalysis(Issue issue) {
    final pinned = _refController.text.trim();
    final key = AnalysisCache.keyFor(
      widget.repository.owner,
      widget.repository.repo,
      issue.number,
      ref: pinned.isEmpty ? null : pinned,
    );
    final analysis = widget.cache.read(key);
    return analysis?.status == AnalysisStatus.completed;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: AppBackground(
        child: PageBody(
          padding: const EdgeInsets.fromLTRB(28, 20, 28, 28),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              RepositoryHeader(
                repository: widget.repository,
                onBack: widget.onBack,
              ),
              const SizedBox(height: AppSpacing.section),
              SnapshotStatus(
                status: _snapshotStatus,
                sha: _snapshotSha,
                fileCount: _snapshotFileCount,
                error: _snapshotError,
                percent: _snapshotPercent,
              ),
              const SizedBox(height: AppSpacing.section),
              Row(
                children: [
                  Text(
                    'Issues',
                    style: AppTypography.title.copyWith(fontSize: 16),
                  ),
                  if (!_loading) ...[
                    const SizedBox(width: 10),
                    Text(
                      '${_visible.length} of ${_issues.length}',
                      style: AppTypography.caption,
                    ),
                  ],
                ],
              ),
              const SizedBox(height: 12),
              Container(
                decoration: BoxDecoration(
                  color: AppTheme.surfaceElevated,
                  borderRadius: AppRadii.panel,
                  border: Border.all(color: AppTheme.borderSubtle),
                ),
                clipBehavior: Clip.antiAlias,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    _buildFilterBar(),
                    Container(height: 1, color: AppTheme.borderSubtle),
                    _buildListBody(),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildFilterBar() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8),
      child: Row(
        children: [
          Expanded(
            flex: 3,
            child: TextField(
              controller: _searchController,
              onChanged: (value) => setState(() => _query = value),
              style: const TextStyle(fontSize: 13),
              decoration: const InputDecoration(
                isDense: true,
                filled: false,
                border: InputBorder.none,
                enabledBorder: InputBorder.none,
                focusedBorder: InputBorder.none,
                contentPadding: EdgeInsets.symmetric(vertical: 14),
                hintText: 'Filter by number, title or description',
                prefixIcon: Icon(
                  Icons.search,
                  size: 16,
                  color: AppTheme.textMuted,
                ),
                prefixIconConstraints: BoxConstraints(minWidth: 36),
              ),
            ),
          ),
          Container(width: 1, height: 28, color: AppTheme.borderSubtle),
          Expanded(
            flex: 2,
            child: TextField(
              controller: _refController,
              onChanged: (_) => setState(() {}),
              style: const TextStyle(fontFamily: AppTheme.mono, fontSize: 12),
              decoration: const InputDecoration(
                isDense: true,
                filled: false,
                border: InputBorder.none,
                enabledBorder: InputBorder.none,
                focusedBorder: InputBorder.none,
                contentPadding: EdgeInsets.symmetric(vertical: 14),
                hintText: 'Commit SHA or ref (optional), Leave blank for main',
                prefixIcon: Icon(
                  Icons.commit,
                  size: 15,
                  color: AppTheme.textMuted,
                ),
                prefixIconConstraints: BoxConstraints(minWidth: 32),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildListBody() {
    if (_loading) {
      return Shimmer(
        child: Column(
          children: List.generate(5, (i) {
            return Column(
              children: [
                if (i > 0) Container(height: 1, color: AppTheme.borderSubtle),
                const IssueRowSkeleton(),
              ],
            );
          }),
        ),
      );
    }

    if (_error != null) {
      return Padding(
        padding: const EdgeInsets.all(16),
        child: ErrorNotice(message: _error!, onRetry: _load),
      );
    }

    if (_visible.isEmpty) {
      return Padding(
        padding: const EdgeInsets.all(16),
        child: EmptyNotice(
          icon: _issues.isEmpty ? Icons.inbox_outlined : Icons.search_off,
          message: _issues.isEmpty
              ? 'This repository has no open issues.'
              : 'No issues match "$_query".',
        ),
      );
    }

    final visible = _visible;
    return Column(
      children: [
        for (var i = 0; i < visible.length; i++) ...[
          if (i > 0) Container(height: 1, color: AppTheme.borderSubtle),
          IssueRow(
            issue: visible[i],
            analyzeEnabled: _snapshotStatus != 'preparing',
            analyzed: _hasCompletedAnalysis(visible[i]),
            onAnalyze: () => widget.onIssueSelected(
              visible[i],
              ref: _refController.text.trim().isEmpty
                  ? null
                  : _refController.text.trim(),
            ),
          ),
        ],
      ],
    );
  }
}

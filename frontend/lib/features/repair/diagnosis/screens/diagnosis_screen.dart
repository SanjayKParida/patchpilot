import 'dart:async';

import 'package:flutter/material.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/core/widgets/common.dart';
import 'package:patchpilot_web/features/repair/code_viewer/screens/code_viewer_screen.dart';
import 'package:patchpilot_web/features/repair/patch/widgets/patch_panel.dart';
import 'package:patchpilot_web/features/repair/shell/repair_header.dart';
import 'package:patchpilot_web/features/repair/shell/repair_inspector.dart';
import 'package:patchpilot_web/features/repair/shell/repair_shell.dart';
import 'package:patchpilot_web/features/repair/shell/repair_status_bar.dart';
import 'package:patchpilot_web/features/repair/shell/repair_workflow.dart';
import 'package:patchpilot_web/models/models.dart';
import 'package:patchpilot_web/services/analysis_cache.dart';
import 'package:patchpilot_web/services/api_client.dart';

import '../widgets/explanation_section.dart';
import '../widgets/follow_up.dart';
import '../widgets/open_file_button.dart';
import '../widgets/relevant_files_section.dart';
import '../widgets/root_cause_section.dart';
import '../widgets/status_banner.dart';

/// The product. Everything else exists to get the user here.
///
/// Starts an analysis, follows it through the pipeline, and lays out
/// the result so the diagnosis is read first and the evidence behind
/// it is available immediately below.
class DiagnosisScreen extends StatefulWidget {
  final ApiClient api;
  final AnalysisCache cache;
  final Repository repository;
  final Issue issue;
  final String? ref;
  final VoidCallback onBack;

  const DiagnosisScreen({
    super.key,
    required this.api,
    required this.cache,
    required this.repository,
    required this.issue,
    required this.onBack,
    this.ref,
  });

  @override
  State<DiagnosisScreen> createState() => _DiagnosisScreenState();
}

class _DiagnosisScreenState extends State<DiagnosisScreen> {
  static const _previewLimit = 5;

  StreamSubscription<Analysis>? _subscription;

  Analysis? _analysis;
  String? _error;
  bool _fromCache = false;
  bool _filesExpanded = false;
  bool _showInspector = true;

  String get _cacheKey => AnalysisCache.keyFor(
    widget.repository.owner,
    widget.repository.repo,
    widget.issue.number,
    ref: widget.ref,
  );

  @override
  void initState() {
    super.initState();

    final cached = widget.cache.read(_cacheKey);

    if (cached != null) {
      // Already analysed this session. Show it rather than spending
      // another forty seconds and two model calls on the same answer.
      _analysis = cached;
      _fromCache = true;
      return;
    }

    _start();
  }

  /// Discard the cached result and analyse again from scratch.
  Future<void> _reanalyze() async {
    widget.cache.invalidate(_cacheKey);
    setState(() => _fromCache = false);
    await _start();
  }

  @override
  void dispose() {
    _subscription?.cancel();
    super.dispose();
  }

  Future<void> _start() async {
    setState(() {
      _analysis = null;
      _error = null;
    });

    await _subscription?.cancel();

    try {
      final created = await widget.api.startAnalysis(
        owner: widget.repository.owner,
        repo: widget.repository.repo,
        issueNumber: widget.issue.number,
        ref: widget.ref,
      );

      if (!mounted) return;
      setState(() => _analysis = created);

      _subscription = widget.api
          .watchAnalysis(created.id)
          .listen(
            (analysis) {
              if (!mounted) return;
              setState(() => _analysis = analysis);
              widget.cache.save(_cacheKey, analysis);
            },
            onError: (Object e) {
              if (mounted) setState(() => _error = e.toString());
            },
          );
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
    }
  }

  /// Open a file's source, optionally landing on a specific line.
  ///
  /// Every claim on this screen routes through here, so "show me why"
  /// is always one tap from the assertion that prompted it.
  void _openFile(String path, {int? line, String? reason}) {
    final analysis = _analysis;
    if (analysis == null || analysis.id.isEmpty) return;

    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => CodeViewerScreen(
          api: widget.api,
          cache: widget.cache,
          analysisId: analysis.id,
          path: path,
          highlightLine: line,
          reason: reason,
        ),
      ),
    );
  }

  /// Open a ranked file. The section reports only the file; this
  /// screen chooses the evidence line the viewer should land on.
  void _openRelevantFile(RelevantFile file) {
    final item = file.evidence.isNotEmpty ? file.evidence.first : null;
    _openFile(
      file.path,
      line: item?.line,
      reason: item == null ? null : '${item.kind} ${item.identifier}',
    );
  }

  List<RelevantFile> _visibleFiles(Analysis analysis) {
    if (_filesExpanded) return analysis.relevantFiles;
    if (analysis.relevantFiles.length <= _previewLimit) {
      return analysis.relevantFiles;
    }
    return analysis.relevantFiles.take(_previewLimit).toList();
  }

  @override
  Widget build(BuildContext context) {
    final analysis = _analysis;

    return RepairShell(
      header: RepairHeader(
        repositoryFullName: widget.repository.fullName,
        branch: _headerBranch,
        commitSha: _headerCommitSha,
        statusLabel: _headerStatusLabel,
        statusColor: _headerStatusColor,
        isInspectorVisible: _showInspector,
        onToggleInspector: () {
          setState(() => _showInspector = !_showInspector);
        },
      ),
      workflow: const RepairWorkflow(
        currentStage: RepairStage.diagnosis,
        completedStages: {RepairStage.issue},
      ),
      content: PageBody(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _buildIssueHeader(),
            const SizedBox(height: 20),
            if (_error != null)
              ErrorNotice(message: _error!, onRetry: _start)
            else if (analysis == null)
              const StatusBanner(
                status: AnalysisStatus.queued,
                label: 'Starting analysis',
              )
            else ...[
              StatusBanner(
                status: analysis.status,
                label: analysis.status == AnalysisStatus.failed
                    ? (analysis.error ?? 'Analysis failed')
                    : _fromCache
                    ? 'Showing the result from earlier in this '
                          'session'
                    : analysis.stageLabel,
                onRetry: analysis.status == AnalysisStatus.failed
                    ? _start
                    : null,
                onReanalyze: analysis.status == AnalysisStatus.completed
                    ? _reanalyze
                    : null,
              ),
              if (analysis.signals.isNotEmpty) ...[
                const SizedBox(height: 28),
                const SectionTitle('Signals'),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: analysis.signals
                      .map(
                        (signal) => StatusChip(
                          label: signal.term,
                          color: AppTheme.signalColor(signal.type),
                        ),
                      )
                      .toList(),
                ),
              ],
              if (analysis.diagnosis != null) ...[
                const SizedBox(height: 28),
                RootCauseSection(
                  diagnosis: analysis.diagnosis!,
                  onViewRootCause: (path, line) => _openFile(path, line: line),
                ),
              ] else if (analysis.diagnosisError != null &&
                  analysis.status == AnalysisStatus.completed) ...[
                const SizedBox(height: 28),
                const SectionTitle('Root cause'),
                ErrorNotice(message: analysis.diagnosisError!),
              ],
              if (analysis.relevantFiles.isNotEmpty) ...[
                const SizedBox(height: 28),
                RelevantFilesSection(
                  files: analysis.relevantFiles,
                  visibleFiles: _visibleFiles(analysis),
                  isExpanded: _filesExpanded,
                  onExpandedChanged: (expanded) =>
                      setState(() => _filesExpanded = expanded),
                  onOpen: _openRelevantFile,
                  citedFilePaths: {...?analysis.diagnosis?.citedFiles},
                  totalSignalCount: analysis.signals.length,
                ),
              ],
              if (analysis.diagnosis != null) ...[
                const SizedBox(height: 28),
                ExplanationSection(diagnosis: analysis.diagnosis!),
                const SizedBox(height: 28),
                const SectionTitle('Suggested fix'),
                Panel(
                  background: AppTheme.success.withValues(alpha: 0.06),
                  borderColor: AppTheme.success.withValues(alpha: 0.35),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Icon(
                            Icons.build_outlined,
                            size: 20,
                            color: AppTheme.success,
                          ),
                          const SizedBox(width: 14),
                          Expanded(
                            child: SelectableText(
                              analysis.diagnosis!.suggestedFix,
                              style: const TextStyle(fontSize: 15, height: 1.7),
                            ),
                          ),
                        ],
                      ),
                      if (analysis.diagnosis!.citedFiles.isNotEmpty) ...[
                        const SizedBox(height: 16),
                        const Divider(height: 1, color: AppTheme.border),
                        const SizedBox(height: 12),
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: analysis.diagnosis!.citedFiles
                              .map(
                                (path) => OpenFileButton(
                                  path: path,
                                  onTap: () => _openFile(path),
                                ),
                              )
                              .toList(),
                        ),
                      ],
                    ],
                  ),
                ),
              ],
              if (analysis.status == AnalysisStatus.completed &&
                  analysis.diagnosis != null) ...[
                const SizedBox(height: 28),
                PatchPanel(
                  api: widget.api,
                  analysisId: analysis.id,
                  commitSha: analysis.commitSha,
                  requestedRef: widget.ref,
                  onOpenFile: (path, {int? line, String? reason}) =>
                      _openFile(path, line: line, reason: reason),
                ),
                const SizedBox(height: 28),
                FollowUpPanel(api: widget.api, analysisId: analysis.id),
              ],
            ],
            const SizedBox(height: 48),
          ],
        ),
      ),
      inspector: RepairInspector(
        title: 'Inspector',
        onClose: () => setState(() => _showInspector = false),
        child: const Text(
          'Evidence will appear here',
          style: TextStyle(color: AppTheme.textMuted, fontSize: 12.5),
        ),
      ),
      showInspector: _showInspector,
      statusBar: RepairStatusBar(
        statusLabel: _statusBarLabel,
        supportingText: _statusBarSupportingText,
        statusIcon: _statusBarIcon,
        tone: _statusBarTone,
        isLoading: _statusBarLoading,
      ),
    );
  }

  String? get _analyzedCommit {
    final sha = _analysis?.commitSha?.trim();
    if (sha != null && sha.isNotEmpty) return sha;
    final requested = widget.ref?.trim();
    if (requested != null && requested.isNotEmpty) return requested;
    return null;
  }

  String get _headerBranch {
    final requested = widget.ref?.trim();
    if (requested != null && requested.isNotEmpty) return requested;
    final resolved = _analysis?.ref?.trim();
    if (resolved != null && resolved.isNotEmpty) return resolved;
    return 'HEAD';
  }

  String get _headerCommitSha => (_analysis?.commitSha ?? '').trim();

  String get _headerStatusLabel {
    if (_error != null &&
        (_analysis == null || _analysis!.status == AnalysisStatus.failed)) {
      return 'Analysis failed';
    }
    final analysis = _analysis;
    if (analysis == null) return 'Starting analysis';
    switch (analysis.status) {
      case AnalysisStatus.queued:
      case AnalysisStatus.running:
        return 'Analyzing';
      case AnalysisStatus.completed:
        return 'Analysis complete';
      case AnalysisStatus.failed:
        return 'Analysis failed';
    }
  }

  Color get _headerStatusColor {
    if (_error != null && _analysis == null) return AppTheme.danger;
    final analysis = _analysis;
    if (analysis == null) return AppTheme.accent;
    switch (analysis.status) {
      case AnalysisStatus.queued:
      case AnalysisStatus.running:
        return AppTheme.accent;
      case AnalysisStatus.completed:
        return AppTheme.success;
      case AnalysisStatus.failed:
        return AppTheme.danger;
    }
  }

  String get _statusBarLabel {
    if (_error != null && _analysis == null) return 'Analysis failed';
    final analysis = _analysis;
    if (analysis == null) return 'Starting analysis';
    switch (analysis.status) {
      case AnalysisStatus.queued:
      case AnalysisStatus.running:
        return analysis.stageLabel;
      case AnalysisStatus.completed:
        return 'Analysis complete';
      case AnalysisStatus.failed:
        return 'Analysis failed';
    }
  }

  String? get _statusBarSupportingText {
    if (_error != null && _analysis == null) return _error;
    final analysis = _analysis;
    if (analysis == null) return null;
    if (analysis.status == AnalysisStatus.failed) {
      return analysis.error;
    }
    if (analysis.status == AnalysisStatus.completed && _fromCache) {
      return 'Showing the result from earlier in this session';
    }
    return null;
  }

  RepairStatusTone get _statusBarTone {
    if (_error != null && _analysis == null) return RepairStatusTone.danger;
    final analysis = _analysis;
    if (analysis == null) return RepairStatusTone.accent;
    switch (analysis.status) {
      case AnalysisStatus.queued:
      case AnalysisStatus.running:
        return RepairStatusTone.accent;
      case AnalysisStatus.completed:
        return RepairStatusTone.success;
      case AnalysisStatus.failed:
        return RepairStatusTone.danger;
    }
  }

  bool get _statusBarLoading {
    if (_error != null) return false;
    final analysis = _analysis;
    if (analysis == null) return true;
    return analysis.status == AnalysisStatus.queued ||
        analysis.status == AnalysisStatus.running;
  }

  IconData? get _statusBarIcon {
    if (_statusBarLoading) return null;
    if (_error != null && _analysis == null) return Icons.error_outline;
    final analysis = _analysis;
    if (analysis == null) return null;
    switch (analysis.status) {
      case AnalysisStatus.completed:
        return Icons.check_circle_outline;
      case AnalysisStatus.failed:
        return Icons.error_outline;
      case AnalysisStatus.queued:
      case AnalysisStatus.running:
        return null;
    }
  }

  static String _shortSha(String value) {
    if (value.length <= 12) return value;
    return value.substring(0, 12);
  }

  Widget _buildIssueHeader() {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        IconButton(
          onPressed: widget.onBack,
          icon: const Icon(Icons.arrow_back),
          tooltip: 'Back to issues',
          color: AppTheme.textMuted,
        ),
        const SizedBox(width: 8),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Text(
                    '#${widget.issue.number}',
                    style: const TextStyle(
                      fontSize: 13,
                      fontFamily: AppTheme.mono,
                      color: AppTheme.textMuted,
                    ),
                  ),
                  const SizedBox(width: 10),
                  Text(
                    widget.repository.fullName,
                    style: const TextStyle(
                      fontSize: 13,
                      color: AppTheme.textMuted,
                    ),
                  ),
                ],
              ),
              if (_analyzedCommit != null) ...[
                const SizedBox(height: 6),
                Tooltip(
                  message: _analyzedCommit!,
                  child: Text(
                    'Analyzed at ${_shortSha(_analyzedCommit!)}',
                    style: const TextStyle(
                      fontSize: 12.5,
                      fontFamily: AppTheme.mono,
                      color: AppTheme.purple,
                    ),
                  ),
                ),
              ],
              const SizedBox(height: 8),
              Text(
                widget.issue.title,
                style: const TextStyle(
                  fontSize: 24,
                  fontWeight: FontWeight.w700,
                  height: 1.3,
                  letterSpacing: -0.4,
                ),
              ),
              if (widget.issue.body.trim().isNotEmpty) ...[
                const SizedBox(height: 12),
                ExpandableText(
                  text: widget.issue.body.trim(),
                  maxLines: _previewLimit,
                  style: const TextStyle(
                    fontSize: 14,
                    color: AppTheme.textMuted,
                    height: 1.6,
                  ),
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }
}

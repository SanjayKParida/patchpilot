// diagnosis_screen.dart
import 'dart:async';

import 'package:flutter/material.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/core/widgets/common.dart';
import 'package:patchpilot_web/core/widgets/motion.dart';
import 'package:patchpilot_web/features/repair/code_viewer/screens/code_viewer_screen.dart';
import 'package:patchpilot_web/models/models.dart';
import 'package:patchpilot_web/services/analysis_cache.dart';
import 'package:patchpilot_web/services/api_client.dart';

import '../../shell/repair_section_help.dart';
import '../widgets/explanation_section.dart';
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
  final String? resumeAnalysisId;
  final VoidCallback onBack;
  final void Function(Analysis? analysis, String? error, bool fromCache)?
  onSessionUpdate;

  const DiagnosisScreen({
    super.key,
    required this.api,
    required this.cache,
    required this.repository,
    required this.issue,
    required this.onBack,
    this.ref,
    this.resumeAnalysisId,
    this.onSessionUpdate,
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

  String get _cacheKey => AnalysisCache.keyFor(
    widget.repository.owner,
    widget.repository.repo,
    widget.issue.number,
    ref: widget.ref,
  );

  @override
  void initState() {
    super.initState();

    final resumeId = widget.resumeAnalysisId?.trim();
    if (resumeId != null && resumeId.isNotEmpty) {
      _resume(resumeId);
      return;
    }

    final cached = widget.cache.read(_cacheKey);

    if (cached != null) {
      // Already analysed this session. Show it rather than spending
      // another forty seconds and two model calls on the same answer.
      _analysis = cached;
      _fromCache = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _emitSession();
      });
      return;
    }

    _start();
  }

  void _emitSession() {
    final onUpdate = widget.onSessionUpdate;
    if (onUpdate == null) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      onUpdate(_analysis, _error, _fromCache);
    });
  }

  /// Discard the cached result and analyse again from scratch.
  Future<void> _reanalyze() async {
    widget.cache.invalidate(_cacheKey);
    setState(() => _fromCache = false);
    _emitSession();
    await _start(force: true);
  }

  Future<void> _resume(String id) async {
    await _subscription?.cancel();

    try {
      final analysis = await widget.api.getAnalysis(id);
      if (!mounted) return;
      setState(() {
        _analysis = analysis;
        _fromCache = analysis.isTerminal;
        _error = null;
      });
      widget.cache.save(_cacheKey, analysis);
      _emitSession();
      if (analysis.isTerminal) return;

      _subscription = widget.api
          .watchAnalysis(analysis.id)
          .listen(
            (next) {
              if (!mounted) return;
              setState(() => _analysis = next);
              widget.cache.save(_cacheKey, next);
              _emitSession();
            },
            onError: (Object e) {
              if (!mounted) return;
              setState(() => _error = e.toString());
              _emitSession();
            },
          );
    } on ApiException {
      if (!mounted) return;
      await _start();
    }
  }

  @override
  void dispose() {
    _subscription?.cancel();
    super.dispose();
  }

  Future<void> _start({bool force = false}) async {
    setState(() {
      _analysis = null;
      _error = null;
    });
    _emitSession();

    await _subscription?.cancel();

    try {
      final created = await widget.api.startAnalysis(
        owner: widget.repository.owner,
        repo: widget.repository.repo,
        issueNumber: widget.issue.number,
        ref: widget.ref,
        force: force,
      );

      if (!mounted) return;
      final reused = !force && created.isTerminal;
      setState(() {
        _analysis = created;
        _fromCache = reused;
      });
      widget.cache.save(_cacheKey, created);
      _emitSession();

      if (created.isTerminal) return;

      _subscription = widget.api
          .watchAnalysis(created.id)
          .listen(
            (analysis) {
              if (!mounted) return;
              setState(() => _analysis = analysis);
              widget.cache.save(_cacheKey, analysis);
              _emitSession();
            },
            onError: (Object e) {
              if (!mounted) return;
              setState(() => _error = e.toString());
              _emitSession();
            },
          );
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
      _emitSession();
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

    return SingleChildScrollView(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 20),
      child: Align(
        alignment: Alignment.topCenter,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 1040),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _buildIssueHeader(),
              const SizedBox(height: 22),
              if (_error != null)
                ErrorNotice(message: _error!, onRetry: _start)
              else if (analysis == null ||
                  analysis.status == AnalysisStatus.queued ||
                  analysis.status == AnalysisStatus.running)
                const Shimmer(child: _DiagnosisSkeleton())
              else ...[
                if (analysis.status == AnalysisStatus.completed ||
                    analysis.status == AnalysisStatus.failed)
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
                // 1–2. Root cause + defect location. First content block —
                // this is what the user should read before anything else.
                if (analysis.diagnosis != null) ...[
                  const _SectionBreak(strong: true),
                  RootCauseSection(
                    diagnosis: analysis.diagnosis!,
                    onViewRootCause: (path, line) =>
                        _openFile(path, line: line),
                  ),
                ] else if (analysis.diagnosisError != null &&
                    analysis.status == AnalysisStatus.completed) ...[
                  const _SectionBreak(strong: true),
                  const Row(
                    children: [
                      Text('ROOT CAUSE', style: AppTypography.sectionLabel),
                      SectionInfoButton(message: RepairSectionHelp.rootCause),
                    ],
                  ),
                  const SizedBox(height: 12),
                  ErrorNotice(message: analysis.diagnosisError!),
                ],

                // 3. Why the diagnosis believes this is the root cause.
                if (analysis.diagnosis != null) ...[
                  const _SectionBreak(),
                  ExplanationSection(diagnosis: analysis.diagnosis!),
                ],

                // 4. Relevant files and symbols.
                if (analysis.relevantFiles.isNotEmpty) ...[
                  const _SectionBreak(),
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

                // 5. Supporting evidence — matched signal terms. Kept
                // deliberately quiet: markers, not badges.
                if (analysis.signals.isNotEmpty) ...[
                  const _SectionBreak(),
                  const Row(
                    children: [
                      Text('SIGNALS', style: AppTypography.sectionLabel),
                      SectionInfoButton(message: RepairSectionHelp.signals),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Wrap(
                    spacing: 16,
                    runSpacing: 10,
                    children: analysis.signals
                        .map(
                          (signal) => _SignalMarker(
                            label: signal.term,
                            color: AppTheme.signalColor(signal.type),
                          ),
                        )
                        .toList(),
                  ),
                ],

                // 6. Suggested fix — the conclusion of the investigation.
                if (analysis.diagnosis != null) ...[
                  const _SectionBreak(),
                  const Row(
                    children: [
                      Text('SUGGESTED FIX', style: AppTypography.sectionLabel),
                      SectionInfoButton(
                        message: RepairSectionHelp.suggestedFix,
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  SelectableText(
                    analysis.diagnosis!.suggestedFix,
                    style: const TextStyle(
                      fontSize: 13.5,
                      height: 1.55,
                      color: AppTheme.textSecondary,
                    ),
                  ),
                  if (analysis.diagnosis!.citedFiles.isNotEmpty) ...[
                    const SizedBox(height: 16),
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
              ],
              const SizedBox(height: 48),
            ],
          ),
        ),
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

  static String _shortSha(String value) {
    if (value.length <= 12) return value;
    return value.substring(0, 12);
  }

  Widget _buildIssueHeader() {
    final commit = _analyzedCommit;

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        IconButton(
          onPressed: widget.onBack,
          icon: const Icon(Icons.arrow_back),
          tooltip: 'Back to issues',
          color: AppTheme.textMuted,
        ),
        const SizedBox(width: 4),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Compact metadata line — everything the eye can skip
              // past once it has registered the issue is worth reading.
              Text.rich(
                TextSpan(
                  style: const TextStyle(
                    fontSize: 11.5,
                    fontFamily: AppTheme.mono,
                    color: AppTheme.textMuted,
                    letterSpacing: 0.2,
                  ),
                  children: [
                    const TextSpan(text: 'ISSUE #'),
                    TextSpan(text: '${widget.issue.number}'),
                    const TextSpan(text: '  ·  '),
                    TextSpan(text: widget.repository.fullName),
                    if (commit != null) ...[
                      const TextSpan(text: '  ·  '),
                      TextSpan(text: _shortSha(commit)),
                    ],
                  ],
                ),
                overflow: TextOverflow.ellipsis,
              ),
              const SizedBox(height: 10),
              Text(
                widget.issue.title,
                style: const TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                  height: 1.35,
                  letterSpacing: -0.1,
                  color: AppTheme.text,
                ),
              ),
              if (widget.issue.body.trim().isNotEmpty) ...[
                const SizedBox(height: 8),
                ExpandableText(
                  text: widget.issue.body.trim(),
                  maxLines: _previewLimit,
                  style: const TextStyle(
                    fontSize: 12.5,
                    color: AppTheme.textMuted,
                    height: 1.5,
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

/// One hairline rule with the shared before/after rhythm used to
/// separate every section on the diagnosis screen. [strong] marks the
/// single rule that introduces Root Cause — everything after it steps
/// down to the quieter divider color.
class _SectionBreak extends StatelessWidget {
  const _SectionBreak({this.strong = false});

  final bool strong;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 28, bottom: 20),
      child: Divider(
        height: 1,
        color: strong ? AppTheme.border : AppTheme.borderSubtle,
      ),
    );
  }
}

/// A single piece of supporting evidence — a dot and a term, nothing
/// more. Deliberately subordinate to everything above it.
class _SignalMarker extends StatelessWidget {
  const _SignalMarker({required this.label, required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 5,
          height: 5,
          decoration: BoxDecoration(shape: BoxShape.circle, color: color),
        ),
        const SizedBox(width: 7),
        Text(
          label,
          style: const TextStyle(
            fontSize: 11.5,
            fontFamily: AppTheme.mono,
            color: AppTheme.textMuted,
          ),
        ),
      ],
    );
  }
}

class _DiagnosisSkeleton extends StatelessWidget {
  const _DiagnosisSkeleton();

  @override
  Widget build(BuildContext context) {
    return const Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _SkeletonRootCause(),
        _SkeletonRule(),
        _SkeletonProse(lines: [1.0, 0.92, 0.58]),
        _SkeletonRule(),
        _SkeletonFiles(),
        _SkeletonRule(),
        _SkeletonSignals(),
        _SkeletonRule(),
        _SkeletonProse(lines: [0.86, 0.64]),
      ],
    );
  }
}

class _SkeletonRule extends StatelessWidget {
  const _SkeletonRule();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 20),
      child: Divider(height: 1, color: AppTheme.border.withValues(alpha: 0.55)),
    );
  }
}

class _SkeletonSignals extends StatelessWidget {
  const _SkeletonSignals();

  @override
  Widget build(BuildContext context) {
    return const Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _SkeletonLabel(),
        SizedBox(height: 12),
        Wrap(
          spacing: 18,
          runSpacing: 10,
          children: [
            _SkeletonBar(width: 60, height: 8),
            _SkeletonBar(width: 76, height: 8),
            _SkeletonBar(width: 52, height: 8),
          ],
        ),
      ],
    );
  }
}

class _SkeletonRootCause extends StatelessWidget {
  const _SkeletonRootCause();

  @override
  Widget build(BuildContext context) {
    return const Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _SkeletonLabel(),
        SizedBox(height: 16),
        _SkeletonBar(width: 460, height: 16),
        SizedBox(height: 12),
        _SkeletonBar(height: 10),
        SizedBox(height: 8),
        _SkeletonBar(width: 280, height: 10),
        SizedBox(height: 20),
        _SkeletonBar(width: 220, height: 10),
      ],
    );
  }
}

class _SkeletonFiles extends StatelessWidget {
  const _SkeletonFiles();

  @override
  Widget build(BuildContext context) {
    return const Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _SkeletonLabel(),
        SizedBox(height: 8),
        _SkeletonFileRow(),
        _SkeletonFileRow(),
        _SkeletonFileRow(),
        _SkeletonFileRow(),
      ],
    );
  }
}

class _SkeletonFileRow extends StatelessWidget {
  const _SkeletonFileRow();

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.symmetric(vertical: 10),
      child: Row(
        children: [
          _SkeletonBar(width: 22, height: 8),
          SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _SkeletonBar(width: 168, height: 10),
                SizedBox(height: 6),
                _SkeletonBar(width: 240, height: 8),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _SkeletonProse extends StatelessWidget {
  const _SkeletonProse({required this.lines});

  final List<double> lines;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const _SkeletonLabel(),
        const SizedBox(height: 12),
        for (var i = 0; i < lines.length; i++) ...[
          if (i > 0) const SizedBox(height: 8),
          FractionallySizedBox(
            widthFactor: lines[i],
            alignment: Alignment.centerLeft,
            child: const _SkeletonBar(height: 10),
          ),
        ],
      ],
    );
  }
}

class _SkeletonLabel extends StatelessWidget {
  const _SkeletonLabel();

  @override
  Widget build(BuildContext context) {
    return const _SkeletonBar(width: 86, height: 8);
  }
}

class _SkeletonBar extends StatelessWidget {
  const _SkeletonBar({this.width, this.height = 8});

  final double? width;
  final double height;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: width,
      height: height,
      decoration: BoxDecoration(
        color: AppTheme.border.withValues(alpha: 0.38),
        borderRadius: BorderRadius.circular(2),
      ),
    );
  }
}

import 'dart:async';

import 'package:flutter/material.dart';

import '../models/models.dart';
import '../services/analysis_cache.dart';
import '../services/api_client.dart';
import '../theme.dart';
import '../widgets/common.dart';
import '../widgets/follow_up.dart';
import '../widgets/why_this_file.dart';
import 'code_viewer_screen.dart';

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
  final VoidCallback onBack;

  const DiagnosisScreen({
    super.key,
    required this.api,
    required this.cache,
    required this.repository,
    required this.issue,
    required this.onBack,
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
      );

      if (!mounted) return;
      setState(() => _analysis = created);

      _subscription = widget.api.watchAnalysis(created.id).listen(
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

    return Scaffold(
      body: PageBody(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _buildIssueHeader(),
            const SizedBox(height: 20),
            if (_error != null)
              ErrorNotice(message: _error!, onRetry: _start)
            else if (analysis == null)
              const _StatusBanner(
                status: AnalysisStatus.queued,
                label: 'Starting analysis',
              )
            else ...[
              _StatusBanner(
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
                onReanalyze:
                    analysis.status == AnalysisStatus.completed
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
                _buildRootCause(analysis.diagnosis!),
              ] else if (analysis.diagnosisError != null &&
                  analysis.status == AnalysisStatus.completed) ...[
                const SizedBox(height: 28),
                const SectionTitle('Root cause'),
                ErrorNotice(message: analysis.diagnosisError!),
              ],
              if (analysis.relevantFiles.isNotEmpty) ...[
                const SizedBox(height: 28),
                SectionTitle(
                  'Relevant files',
                  trailing: _filesExpanded ||
                          analysis.relevantFiles.length <= _previewLimit
                      ? 'ranked by evidence'
                      : '$_previewLimit of ${analysis.relevantFiles.length}',
                ),
                ..._visibleFiles(analysis).map(
                  (file) => RelevantFileCard(
                    file: file,
                    totalSignals: analysis.signals.length,
                    cited: analysis.diagnosis?.citedFiles
                            .contains(file.path) ??
                        false,
                    onOpen: ({int? line, String? reason}) => _openFile(
                      file.path,
                      line: line,
                      reason: reason,
                    ),
                  ),
                ),
                if (analysis.relevantFiles.length > _previewLimit)
                  ShowMoreLink(
                    expanded: _filesExpanded,
                    moreLabel:
                        'Show ${analysis.relevantFiles.length - _previewLimit} more',
                    onPressed: () => setState(
                      () => _filesExpanded = !_filesExpanded,
                    ),
                  ),
              ],
              if (analysis.diagnosis != null) ...[
                const SizedBox(height: 28),
                const SectionTitle('Explanation'),
                Panel(
                  child: SelectableText(
                    analysis.diagnosis!.explanation,
                    style: const TextStyle(fontSize: 15, height: 1.7),
                  ),
                ),
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
                              style: const TextStyle(
                                fontSize: 15,
                                height: 1.7,
                              ),
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
                                (path) => _OpenFileButton(
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
                FollowUpPanel(
                  api: widget.api,
                  analysisId: analysis.id,
                ),
              ],
            ],
            const SizedBox(height: 48),
          ],
        ),
      ),
    );
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

  Widget _buildRootCause(Diagnosis diagnosis) {
    final confidenceColor = AppTheme.confidenceColor(
      diagnosis.confidenceBand,
    );

    final rootCause = diagnosis.rootCauseLocation;
    final fallbackFile = diagnosis.affectedFile;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const SectionTitle('Root cause'),
        Panel(
          padding: const EdgeInsets.all(24),
          background: AppTheme.surfaceAlt,
          borderColor: AppTheme.accent.withValues(alpha: 0.4),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SelectableText(
                diagnosis.rootCause,
                style: const TextStyle(
                  fontSize: 19,
                  fontWeight: FontWeight.w600,
                  height: 1.55,
                ),
              ),
              const SizedBox(height: 18),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  StatusChip(
                    label: diagnosis.confidencePercent,
                    color: confidenceColor,
                    icon: Icons.insights,
                  ),
                ],
              ),
              // "View root cause" resolves ONLY from root-cause
              // symbols. If none resolved we open the affected file
              // with no line: an arbitrary supporting symbol is the
              // wrong place to send someone.
              if (rootCause != null) ...[
                const SizedBox(height: 20),
                Row(
                  children: [
                    FilledButton.icon(
                      onPressed: () => _openFile(
                        rootCause.path,
                        line: rootCause.line,
                        reason: rootCause.symbol,
                      ),
                      icon: const Icon(Icons.my_location, size: 17),
                      label: const Text('View root cause'),
                      style: FilledButton.styleFrom(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 18,
                          vertical: 15,
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Flexible(
                      child: Text(
                        '${rootCause.symbol}  ·  ${rootCause.label}',
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 12.5,
                          fontFamily: AppTheme.mono,
                          color: AppTheme.textMuted,
                        ),
                      ),
                    ),
                  ],
                ),
              ] else if (fallbackFile != null) ...[
                const SizedBox(height: 20),
                Row(
                  children: [
                    FilledButton.icon(
                      onPressed: () => _openFile(fallbackFile),
                      icon: const Icon(Icons.description_outlined,
                          size: 17),
                      label: const Text('Open affected file'),
                      style: FilledButton.styleFrom(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 18,
                          vertical: 15,
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Flexible(
                      child: Text(
                        fallbackFile.split('/').last,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 12.5,
                          fontFamily: AppTheme.mono,
                          color: AppTheme.textMuted,
                        ),
                      ),
                    ),
                  ],
                ),
              ],
              if (diagnosis.locations.isNotEmpty) ...[
                const SizedBox(height: 18),
                const Divider(height: 1, color: AppTheme.border),
                const SizedBox(height: 14),
                const Text(
                  'RELATED DECLARATIONS',
                  style: TextStyle(
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1,
                    color: AppTheme.textMuted,
                  ),
                ),
                const SizedBox(height: 10),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: diagnosis.locations
                      .map(
                        (location) => _SymbolButton(
                          location: location,
                          onTap: () => _openFile(
                            location.path,
                            line: location.line,
                            reason: location.symbol,
                          ),
                        ),
                      )
                      .toList(),
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }
}

class _StatusBanner extends StatelessWidget {
  final AnalysisStatus status;
  final String label;
  final VoidCallback? onRetry;
  final VoidCallback? onReanalyze;

  const _StatusBanner({
    required this.status,
    required this.label,
    this.onRetry,
    this.onReanalyze,
  });

  @override
  Widget build(BuildContext context) {
    late final Color color;
    late final Widget leading;
    late final String title;

    switch (status) {
      case AnalysisStatus.completed:
        color = AppTheme.success;
        title = 'Analysis complete';
        leading = const Icon(
          Icons.check_circle_outline,
          size: 18,
          color: AppTheme.success,
        );
      case AnalysisStatus.failed:
        color = AppTheme.danger;
        title = 'Analysis failed';
        leading = const Icon(
          Icons.error_outline,
          size: 18,
          color: AppTheme.danger,
        );
      case AnalysisStatus.queued:
      case AnalysisStatus.running:
        color = AppTheme.accent;
        title = 'Analyzing';
        leading = const SizedBox(
          width: 16,
          height: 16,
          child: CircularProgressIndicator(
            strokeWidth: 2,
            color: AppTheme.accent,
          ),
        );
    }

    return Panel(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
      background: color.withValues(alpha: 0.07),
      borderColor: color.withValues(alpha: 0.35),
      child: Row(
        children: [
          leading,
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                    color: color,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  label,
                  style: const TextStyle(
                    fontSize: 13,
                    color: AppTheme.textMuted,
                    height: 1.4,
                  ),
                ),
              ],
            ),
          ),
          if (onRetry != null)
            TextButton(onPressed: onRetry, child: const Text('Retry')),
          if (onReanalyze != null)
            TextButton(
              onPressed: onReanalyze,
              child: const Text('Re-analyze'),
            ),
        ],
      ),
    );
  }
}


/// A file path rendered as an affordance rather than as text.
class _OpenFileButton extends StatelessWidget {
  final String path;
  final VoidCallback onTap;

  const _OpenFileButton({required this.path, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(6),
        child: Container(
          padding: const EdgeInsets.symmetric(
            horizontal: 10,
            vertical: 7,
          ),
          decoration: BoxDecoration(
            color: AppTheme.background,
            border: Border.all(
              color: AppTheme.accent.withValues(alpha: 0.4),
            ),
            borderRadius: BorderRadius.circular(6),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.code, size: 13, color: AppTheme.accent),
              const SizedBox(width: 7),
              Text(
                path.split('/').last,
                style: const TextStyle(
                  fontSize: 12,
                  fontFamily: AppTheme.mono,
                  color: AppTheme.accent,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}


/// A resolved declaration, rendered as somewhere you can go.
class _SymbolButton extends StatelessWidget {
  final SymbolLocation location;
  final VoidCallback onTap;

  const _SymbolButton({required this.location, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(6),
        child: Container(
          padding: const EdgeInsets.symmetric(
            horizontal: 10,
            vertical: 7,
          ),
          decoration: BoxDecoration(
            color: AppTheme.background,
            border: Border.all(
              color: AppTheme.purple.withValues(alpha: 0.45),
            ),
            borderRadius: BorderRadius.circular(6),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                Icons.my_location,
                size: 13,
                color: AppTheme.purple,
              ),
              const SizedBox(width: 7),
              Text(
                location.symbol,
                style: const TextStyle(
                  fontSize: 12,
                  fontFamily: AppTheme.mono,
                  color: AppTheme.text,
                ),
              ),
              const SizedBox(width: 8),
              Text(
                location.label,
                style: const TextStyle(
                  fontSize: 11.5,
                  fontFamily: AppTheme.mono,
                  color: AppTheme.textMuted,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

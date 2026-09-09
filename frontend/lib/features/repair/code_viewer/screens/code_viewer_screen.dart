import 'package:flutter/material.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/core/widgets/app_background.dart';
import 'package:patchpilot_web/core/widgets/common.dart';
import 'package:patchpilot_web/features/repair/code_viewer/widgets/code_file_header.dart';
import 'package:patchpilot_web/features/repair/code_viewer/widgets/source_code_viewer.dart';
import 'package:patchpilot_web/features/repair/code_viewer/widgets/syntax_highlighter.dart';
import 'package:patchpilot_web/models/models.dart';
import 'package:patchpilot_web/services/analysis_cache.dart';
import 'package:patchpilot_web/services/api_client.dart';

/// Shows the source behind a claim.
class CodeViewerScreen extends StatefulWidget {
  final ApiClient api;
  final AnalysisCache cache;
  final String analysisId;
  final String path;
  final int? highlightLine;
  final String? reason;

  const CodeViewerScreen({
    super.key,
    required this.api,
    required this.cache,
    required this.analysisId,
    required this.path,
    this.highlightLine,
    this.reason,
  });

  @override
  State<CodeViewerScreen> createState() => _CodeViewerScreenState();
}

class _CodeViewerScreenState extends State<CodeViewerScreen> {
  static const _viewerFontSize = 13;
  static const _viewerLineHeightFactor = 1.7;

  final _viewerKey = GlobalKey();

  FileSource? _file;
  String? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final cached = widget.cache.readFile(widget.analysisId, widget.path);

    if (cached != null) {
      setState(() {
        _file = cached;
        _loading = false;
      });
      _scrollToHighlight();
      return;
    }

    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final file = await widget.api.getAnalysisFile(
        widget.analysisId,
        widget.path,
      );

      if (!mounted) return;
      widget.cache.saveFile(widget.analysisId, file);
      setState(() => _file = file);
      _scrollToHighlight();
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _scrollToHighlight() {
    final line = widget.highlightLine;
    if (line == null || line <= 0) return;

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;

      final context = _viewerKey.currentContext;
      if (context == null) return;

      final scrollable = _verticalCodeScrollable(context);
      if (scrollable == null || !scrollable.position.hasContentDimensions) {
        return;
      }

      final position = scrollable.position;
      final lineHeight = _viewerFontSize * _viewerLineHeightFactor;
      final target = (line - 1) * lineHeight - position.viewportDimension / 3;

      position.animateTo(
        target.clamp(0.0, position.maxScrollExtent),
        duration: const Duration(milliseconds: 320),
        curve: Curves.easeOutCubic,
      );
    });
  }

  ScrollableState? _verticalCodeScrollable(BuildContext context) {
    ScrollableState? found;

    void visit(Element element) {
      if (found != null) return;

      final candidate = element.widget;
      if (candidate is Scrollable) {
        final vertical =
            axisDirectionToAxis(candidate.axisDirection) == Axis.vertical;
        if (vertical && candidate.physics is! NeverScrollableScrollPhysics) {
          found = (element as StatefulElement).state as ScrollableState;
          return;
        }
      }

      element.visitChildren(visit);
    }

    context.visitChildElements(visit);
    return found;
  }

  @override
  Widget build(BuildContext context) {
    final path = _file?.path ?? widget.path;
    final segments = path.split('/');
    final fileName = segments.last;
    final directory = segments.length > 1
        ? segments.sublist(0, segments.length - 1).join('/')
        : '';

    return Scaffold(
      backgroundColor: Colors.transparent,
      body: AppBackground(
        accent: AppTheme.stageDiagnosis,
        child: SafeArea(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              ColoredBox(
                color: AppTheme.surface.withValues(alpha: 0.82),
                child: Row(
                  children: [
                    IconButton(
                      onPressed: () => Navigator.of(context).pop(),
                      icon: const Icon(Icons.arrow_back),
                      tooltip: 'Back to diagnosis',
                      color: AppTheme.textMuted,
                    ),
                    Expanded(
                      child: CodeFileHeader(
                        fileName: fileName,
                        directoryPath: directory,
                        reason: widget.reason,
                        language: _languageFromPath(path),
                      ),
                    ),
                  ],
                ),
              ),
              const Divider(height: 1, color: AppTheme.border),
              Expanded(
                child: _loading
                    ? const Center(child: CircularProgressIndicator())
                    : _error != null
                    ? Padding(
                        padding: const EdgeInsets.all(24),
                        child: ErrorNotice(message: _error!, onRetry: _load),
                      )
                    : SourceCodeViewer(
                        key: _viewerKey,
                        source: _file!.content,
                        highlightedLine: widget.highlightLine,
                        language: SyntaxHighlighter.languageFromPath(
                          widget.path,
                        ),
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// Best-effort language label from a file extension. Unknown
  /// extensions stay unlabeled rather than guessing.
  static String? _languageFromPath(String path) {
    final name = path.split('/').last;
    final dot = name.lastIndexOf('.');
    if (dot <= 0 || dot == name.length - 1) return null;

    const known = {
      'dart': 'Dart',
      'ts': 'TypeScript',
      'tsx': 'TypeScript',
      'js': 'JavaScript',
      'jsx': 'JavaScript',
      'mjs': 'JavaScript',
      'cjs': 'JavaScript',
      'py': 'Python',
    };

    return known[name.substring(dot + 1).toLowerCase()];
  }
}

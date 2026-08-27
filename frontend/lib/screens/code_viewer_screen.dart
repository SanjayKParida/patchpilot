import 'package:flutter/material.dart';

import '../models/models.dart';
import '../services/analysis_cache.dart';
import '../services/api_client.dart';
import '../theme.dart';
import '../widgets/common.dart';

/// Shows the source behind a claim.
///
/// The whole point of the diagnosis screen is that every assertion is
/// backed by code the user can check. This is where they check it.
/// When opened from a piece of evidence it scrolls to, and highlights,
/// the line that evidence came from.
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
  static const double _lineHeight = 21;

  final _scrollController = ScrollController();

  FileSource? _file;
  String? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    // Source belongs to a frozen snapshot and cannot change while the
    // analysis exists, so opening the same file twice — which happens
    // constantly when following evidence — should not refetch it.
    final cached = widget.cache.readFile(
      widget.analysisId,
      widget.path,
    );

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

  /// Put the highlighted line a third of the way down rather than at
  /// the very top, so its surrounding context is visible.
  void _scrollToHighlight() {
    final line = widget.highlightLine;
    if (line == null || line <= 0) return;

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollController.hasClients) return;

      final viewport = _scrollController.position.viewportDimension;
      final target = (line - 1) * _lineHeight - viewport / 3;

      _scrollController.animateTo(
        target.clamp(0.0, _scrollController.position.maxScrollExtent),
        duration: const Duration(milliseconds: 320),
        curve: Curves.easeOutCubic,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final segments = widget.path.split('/');
    final fileName = segments.last;
    final directory =
        segments.length > 1 ? segments.sublist(0, segments.length - 1).join('/') : '';

    return Scaffold(
      body: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _buildHeader(fileName, directory),
            const Divider(height: 1, color: AppTheme.border),
            Expanded(
              child: _loading
                  ? const Center(child: CircularProgressIndicator())
                  : _error != null
                      ? Padding(
                          padding: const EdgeInsets.all(24),
                          child: ErrorNotice(
                            message: _error!,
                            onRetry: _load,
                          ),
                        )
                      : _buildCode(),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader(String fileName, String directory) {
    return Container(
      color: AppTheme.surface,
      padding: const EdgeInsets.fromLTRB(8, 12, 20, 12),
      child: Row(
        children: [
          IconButton(
            onPressed: () => Navigator.of(context).pop(),
            icon: const Icon(Icons.arrow_back),
            tooltip: 'Back to diagnosis',
            color: AppTheme.textMuted,
          ),
          const SizedBox(width: 4),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  fileName,
                  style: const TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w600,
                    fontFamily: AppTheme.mono,
                  ),
                ),
                if (directory.isNotEmpty)
                  Text(
                    directory,
                    style: const TextStyle(
                      fontSize: 12,
                      fontFamily: AppTheme.mono,
                      color: AppTheme.textMuted,
                    ),
                  ),
              ],
            ),
          ),
          if (widget.reason != null) ...[
            const SizedBox(width: 16),
            Flexible(
              child: StatusChip(
                label: widget.reason!,
                color: AppTheme.accent,
                icon: Icons.my_location,
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildCode() {
    final lines = _file!.content.split('\n');
    final gutterWidth = 26.0 + '${lines.length}'.length * 9;

    return Scrollbar(
      controller: _scrollController,
      child: ListView.builder(
        controller: _scrollController,
        itemCount: lines.length,
        itemExtent: _lineHeight,
        padding: const EdgeInsets.only(bottom: 120),
        itemBuilder: (context, index) {
          final number = index + 1;
          final highlighted = number == widget.highlightLine;

          return Container(
            color: highlighted
                ? AppTheme.accent.withValues(alpha: 0.16)
                : null,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Container(
                  width: gutterWidth,
                  alignment: Alignment.centerRight,
                  padding: const EdgeInsets.only(right: 12),
                  decoration: BoxDecoration(
                    border: Border(
                      left: BorderSide(
                        width: 3,
                        color: highlighted
                            ? AppTheme.accent
                            : Colors.transparent,
                      ),
                    ),
                  ),
                  child: Text(
                    '$number',
                    style: TextStyle(
                      fontSize: 12.5,
                      fontFamily: AppTheme.mono,
                      color: highlighted
                          ? AppTheme.accent
                          : AppTheme.textMuted.withValues(alpha: 0.65),
                    ),
                  ),
                ),
                Expanded(
                  child: SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: Padding(
                      padding: const EdgeInsets.only(right: 24),
                      child: Align(
                        alignment: Alignment.centerLeft,
                        child: Text(
                          lines[index],
                          softWrap: false,
                          style: const TextStyle(
                            fontSize: 13,
                            height: 1.45,
                            fontFamily: AppTheme.mono,
                            color: AppTheme.text,
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}

// features/repair/context/screens/context_screen.dart
//
// The Context artifact: presents the backend-selected ContextPackage for a
// diagnosis. This widget does not diagnose, rank, or patch — it loads a
// ContextPackage (from cache or the API) and renders it, in the order the
// backend provided, as a section of the Patch stage.

import 'package:flutter/material.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/core/widgets/common.dart';
import 'package:patchpilot_web/features/repair/code_viewer/screens/code_viewer_screen.dart';
import 'package:patchpilot_web/features/repair/shell/repair_section_help.dart';
import 'package:patchpilot_web/features/repair/shell/repair_workflow.dart';
import 'package:patchpilot_web/models/context_package.dart';
import 'package:patchpilot_web/models/models.dart';
import 'package:patchpilot_web/services/analysis_cache.dart';
import 'package:patchpilot_web/services/api_client.dart';

import '../widgets/context_slice_row.dart';
import '../widgets/context_summary_bar.dart';
import '../widgets/context_warning_banner.dart';

class ContextScreen extends StatefulWidget {
  final ApiClient api;
  final AnalysisCache cache;
  final Repository repository;
  final Issue issue;
  final String analysisId;
  final VoidCallback onBack;
  final ValueChanged<RepairStage>? onNavigateStage;
  final ValueChanged<ContextSlice?>? onInspectedSliceChanged;
  final String? ref;

  const ContextScreen({
    super.key,
    required this.api,
    required this.cache,
    required this.repository,
    required this.issue,
    required this.analysisId,
    required this.onBack,
    this.onNavigateStage,
    this.onInspectedSliceChanged,
    this.ref,
  });

  @override
  State<ContextScreen> createState() => _ContextScreenState();
}

enum _LoadStatus { loading, loaded, error }

class _ContextScreenState extends State<ContextScreen> {
  _LoadStatus _status = _LoadStatus.loading;
  ContextPackage? _package;
  Object? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(ContextScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.analysisId != widget.analysisId ||
        oldWidget.ref != widget.ref ||
        oldWidget.repository.fullName != widget.repository.fullName ||
        oldWidget.issue.number != widget.issue.number) {
      _load();
    }
  }

  Future<void> _load() async {
    setState(() {
      _status = _LoadStatus.loading;
      _error = null;
    });

    final cached = widget.cache.readContext(widget.analysisId);
    if (cached != null) {
      setState(() {
        _package = cached;
        _status = _LoadStatus.loaded;
      });
      return;
    }

    try {
      final package = await widget.api.getContextPackage(widget.analysisId);
      widget.cache.saveContext(widget.analysisId, package);
      if (!mounted) return;
      setState(() {
        _package = package;
        _status = _LoadStatus.loaded;
      });
    } catch (err) {
      if (!mounted) return;
      setState(() {
        _error = err;
        _status = _LoadStatus.error;
      });
    }
  }

  void _openFile(ContextSlice slice) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => CodeViewerScreen(
          api: widget.api,
          cache: widget.cache,
          analysisId: widget.analysisId,
          path: slice.filePath,
          highlightLine: slice.startLine,
          reason: slice.reason,
        ),
      ),
    );
  }

  void _inspect(ContextSlice slice) {
    widget.onInspectedSliceChanged?.call(slice);
  }

  void _buildPatch() {
    widget.onNavigateStage?.call(RepairStage.patch);
  }

  @override
  Widget build(BuildContext context) {
    return _buildBody();
  }

  Widget _buildBody() {
    switch (_status) {
      case _LoadStatus.loading:
        return const _ContextLoading();
      case _LoadStatus.error:
        return _ContextError(error: _error, onRetry: _load);
      case _LoadStatus.loaded:
        final package = _package!;
        if (package.slices.isEmpty) {
          return const _ContextEmpty();
        }
        return _ContextLoaded(
          package: package,
          onBack: widget.onBack,
          onOpenFile: _openFile,
          onInspect: _inspect,
          onBuildPatch: widget.onNavigateStage == null ? null : _buildPatch,
        );
    }
  }
}

class _ContextLoaded extends StatelessWidget {
  final ContextPackage package;
  final VoidCallback onBack;
  final ValueChanged<ContextSlice> onOpenFile;
  final ValueChanged<ContextSlice> onInspect;
  final VoidCallback? onBuildPatch;

  const _ContextLoaded({
    required this.package,
    required this.onBack,
    required this.onOpenFile,
    required this.onInspect,
    this.onBuildPatch,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 1080),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _ContextHeader(onBack: onBack, package: package),
                  const SizedBox(height: 20),
                  if (package.hasWarnings) ...[
                    ContextWarningBanner(warnings: package.warnings),
                    const SizedBox(height: 20),
                  ],
                  const Row(
                    children: [
                      Text(
                        'SELECTED CONTEXT',
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w600,
                          letterSpacing: 0.6,
                          color: AppTheme.textMuted,
                        ),
                      ),
                      SectionInfoButton(
                        message: RepairSectionHelp.selectedContext,
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Container(
                    decoration: const BoxDecoration(
                      border: Border(
                        top: BorderSide(color: AppTheme.border, width: 1),
                      ),
                    ),
                    child: Column(
                      children: [
                        for (int i = 0; i < package.slices.length; i++)
                          ContextSliceRow(
                            slice: package.slices[i],
                            displayIndex: i + 1,
                            onOpenFile: () => onOpenFile(package.slices[i]),
                            onInspect: () => onInspect(package.slices[i]),
                          ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
        Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 1080),
            child: ContextSummaryBar(
              package: package,
              onBuildPatch: onBuildPatch,
            ),
          ),
        ),
      ],
    );
  }
}

class _ContextHeader extends StatelessWidget {
  final VoidCallback onBack;
  final ContextPackage package;

  const _ContextHeader({required this.onBack, required this.package});

  @override
  Widget build(BuildContext context) {
    final metaParts = [
      if (package.language != null) package.language!,
      if (package.adapter != null) package.adapter!,
    ];

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        InkWell(
          onTap: onBack,
          borderRadius: BorderRadius.circular(4),
          child: const Padding(
            padding: EdgeInsets.only(right: 8, top: 2),
            child: Icon(Icons.arrow_back, size: 16, color: AppTheme.textMuted),
          ),
        ),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Text(
                    'CONTEXT',
                    style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                      letterSpacing: 0.6,
                      color: AppTheme.textMuted,
                    ),
                  ),
                  const SectionInfoButton(message: RepairSectionHelp.context),
                  if (metaParts.isNotEmpty) ...[
                    const SizedBox(width: 8),
                    Text(
                      '· ${metaParts.join(' · ')}',
                      style: const TextStyle(
                        fontSize: 11,
                        color: AppTheme.textMuted,
                      ),
                    ),
                  ],
                ],
              ),
              const SizedBox(height: 4),
              const Text(
                'Supporting evidence for the patch',
                style: TextStyle(
                  fontSize: 12.5,
                  height: 1.35,
                  color: AppTheme.textMuted,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _ContextLoading extends StatelessWidget {
  const _ContextLoading();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 40),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: const [
          _ContextQuietBar(width: 96),
          SizedBox(height: 18),
          _ContextQuietBar(width: double.infinity, height: 10),
          SizedBox(height: 10),
          _ContextQuietBar(width: 320, height: 10),
          SizedBox(height: 10),
          _ContextQuietBar(width: 240, height: 10),
        ],
      ),
    );
  }
}

class _ContextQuietBar extends StatelessWidget {
  const _ContextQuietBar({required this.width, this.height = 8});

  final double width;
  final double height;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: width,
      height: height,
      decoration: BoxDecoration(
        color: AppTheme.surfaceAlt,
        borderRadius: BorderRadius.circular(2),
      ),
    );
  }
}

class _ContextError extends StatelessWidget {
  final Object? error;
  final VoidCallback onRetry;

  const _ContextError({required this.error, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 40),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.error_outline, size: 20, color: AppTheme.danger),
          const SizedBox(height: 8),
          const Text(
            'Could not load context',
            style: TextStyle(fontSize: 15, color: AppTheme.text),
          ),
          const SizedBox(height: 4),
          Text(
            error?.toString() ?? 'Unknown error',
            style: const TextStyle(fontSize: 12.5, color: AppTheme.textMuted),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 12),
          TextButton(
            onPressed: onRetry,
            child: const Text(
              'Retry',
              style: TextStyle(color: AppTheme.accent),
            ),
          ),
        ],
      ),
    );
  }
}

class _ContextEmpty extends StatelessWidget {
  const _ContextEmpty();

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.symmetric(horizontal: 32, vertical: 40),
      child: Text(
        'No context was selected for this diagnosis.',
        style: TextStyle(fontSize: 12.5, color: AppTheme.textMuted),
      ),
    );
  }
}

// validation_screen.dart
import 'package:flutter/material.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/core/widgets/common.dart';
import 'package:patchpilot_web/core/widgets/motion.dart';
import 'package:patchpilot_web/features/repair/shell/repair_section_help.dart';
import 'package:patchpilot_web/models/models.dart';
import 'package:patchpilot_web/services/api_client.dart';

import 'validation_models.dart';
import 'validation_widgets.dart';

/// Validation stage: apply the stored patch and run Flutter checks.
///
/// Loads GET `/patch` to know whether a proposal exists, GET
/// `/patch/validate` for a stored result, and POST `/patch/validate`
/// to run. Does not generate a patch, approve, or open a PR.
class ValidationScreen extends StatefulWidget {
  final ApiClient api;
  final String analysisId;
  final PatchProposal? initialProposal;
  final PatchValidationResult? initialValidation;
  final ValueChanged<PatchProposal?>? onProposalChanged;
  final ValueChanged<PatchValidationResult?>? onValidationChanged;
  final ValueChanged<bool>? onRunningChanged;

  const ValidationScreen({
    super.key,
    required this.api,
    required this.analysisId,
    this.initialProposal,
    this.initialValidation,
    this.onProposalChanged,
    this.onValidationChanged,
    this.onRunningChanged,
  });

  @override
  State<ValidationScreen> createState() => _ValidationScreenState();
}

class _ValidationScreenState extends State<ValidationScreen> {
  bool _loading = true;
  bool _running = false;
  bool _canRun = false;
  PatchProposal? _proposal;
  PatchValidationResult? _result;
  String? _error;

  /// Shape (check ids/labels only) of the most recent *real* result for
  /// this analysis, if any. Used purely to render an honest pipeline
  /// preview while a new run is in flight — never to imply progress or
  /// outcomes we haven't actually observed.
  List<ValidationCheck>? _knownChecks;

  @override
  void initState() {
    super.initState();
    _proposal = widget.initialProposal;
    _result = widget.initialValidation;
    _canRun = widget.initialProposal?.canValidate == true;
    _knownChecks = _checksFromResult(widget.initialValidation, _canRun);
    _loading =
        widget.initialProposal == null && widget.initialValidation == null;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _load();
    });
  }

  @override
  void didUpdateWidget(covariant ValidationScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.analysisId != widget.analysisId) {
      _proposal = widget.initialProposal;
      _result = widget.initialValidation;
      _canRun = widget.initialProposal?.canValidate == true;
      _knownChecks = _checksFromResult(widget.initialValidation, _canRun);
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _load();
      });
    }
  }

  static List<ValidationCheck>? _checksFromResult(
    PatchValidationResult? result,
    bool canRun,
  ) {
    if (result == null) return null;
    final state = ValidationState.fromResult(
      running: false,
      canRun: canRun,
      result: result,
    );
    return state.checks.isEmpty ? null : state.checks;
  }

  bool _isMissingArtifact(ApiException error) {
    return error.statusCode == 502 || error.statusCode == 404;
  }

  void _emit() {
    final onProposal = widget.onProposalChanged;
    final onValidation = widget.onValidationChanged;
    final onRunning = widget.onRunningChanged;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      onProposal?.call(_proposal);
      onValidation?.call(_result);
      onRunning?.call(_running);
    });
  }

  Future<void> _load() async {
    setState(() {
      _loading = _proposal == null && _result == null;
      _error = null;
    });

    PatchProposal? proposal;
    PatchValidationResult? result;
    String? error;

    try {
      proposal = await widget.api.getPatch(widget.analysisId);
    } on ApiException catch (e) {
      if (e.statusCode != 409 && !_isMissingArtifact(e)) {
        error = e.message;
      }
    }

    final canRun = proposal?.canValidate == true;

    if (canRun) {
      try {
        result = await widget.api.getPatchValidation(widget.analysisId);
      } on ApiException catch (e) {
        if (!_isMissingArtifact(e)) error = e.message;
      }
    } else if (proposal != null && proposal.errors.isNotEmpty) {
      error ??= proposal.errors.first;
    }

    if (!mounted) return;
    setState(() {
      _proposal = proposal;
      _canRun = canRun;
      _result = result;
      _error = error;
      _loading = false;
      final checks = _checksFromResult(result, canRun);
      if (checks != null) _knownChecks = checks;
    });
    _emit();
  }

  Future<void> _run() async {
    if (_running || !_canRun) return;

    setState(() {
      _running = true;
      _error = null;
    });
    _emit();

    try {
      final result = await widget.api.validatePatch(widget.analysisId);
      if (!mounted) return;
      setState(() {
        _result = result;
        final checks = _checksFromResult(result, _canRun);
        if (checks != null) _knownChecks = checks;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
    } finally {
      if (mounted) {
        setState(() => _running = false);
        _emit();
      }
    }
  }

  ValidationState get _state => ValidationState.fromResult(
    running: _running,
    canRun: _canRun,
    result: _result,
    errorMessage: _error,
    knownChecks: _knownChecks,
  );

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const SizedBox.shrink();
    }

    final state = _state;

    return PageBody(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _Header(state: state, onStart: _run, onRetry: _run),
          const SizedBox(height: AppSpacing.section),
          _MainContent(state: state),
        ],
      ),
    );
  }
}

class _Header extends StatelessWidget {
  final ValidationState state;
  final VoidCallback? onStart;
  final VoidCallback? onRetry;

  const _Header({required this.state, this.onStart, this.onRetry});

  @override
  Widget build(BuildContext context) {
    final showStart =
        state.overallStatus == ValidationStatus.notStarted &&
        state.canRun &&
        onStart != null;

    final showRetry =
        (state.overallStatus == ValidationStatus.failed ||
            state.overallStatus == ValidationStatus.unavailable) &&
        state.canRun &&
        onRetry != null;

    final isRunning = state.overallStatus == ValidationStatus.running;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            const Expanded(
              child: Row(
                children: [
                  Text(
                    'Validation',
                    style: TextStyle(
                      color: AppTheme.text,
                      fontSize: 22,
                      fontWeight: FontWeight.w600,
                      letterSpacing: -0.3,
                    ),
                  ),
                  SectionInfoButton(message: RepairSectionHelp.validation),
                ],
              ),
            ),
            // The primary-action slot: a real button when one applies,
            // or a status label in the same position while a run is
            // already in flight — so the slot stays meaningful rather
            // than just disappearing.
            if (showStart)
              FilledButton.icon(
                onPressed: onStart,
                icon: const Icon(Icons.play_arrow_rounded, size: 16),
                label: const Text('Run validation'),
              )
            else if (showRetry)
              FilledButton.icon(
                onPressed: onRetry,
                icon: const Icon(Icons.refresh_rounded, size: 16),
                label: const Text('Retry validation'),
              )
            else if (isRunning)
              const _RunningIndicatorLabel(),
          ],
        ),
        const SizedBox(height: 6),
        const Text(
          'Applies the patch on the pinned commit and runs Flutter checks.',
          style: TextStyle(
            color: AppTheme.textMuted,
            fontSize: 12.5,
            height: 1.4,
          ),
        ),
        if (isRunning) ...[
          const SizedBox(height: 12),
          const AppProgressBar(height: 2),
        ],
      ],
    );
  }
}

class _RunningIndicatorLabel extends StatelessWidget {
  const _RunningIndicatorLabel();

  @override
  Widget build(BuildContext context) {
    return const Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        ValidationPulseDot(size: 7),
        SizedBox(width: 8),
        Text(
          'Running…',
          style: TextStyle(
            color: AppTheme.accent,
            fontSize: 12.5,
            fontWeight: FontWeight.w500,
            fontFamily: AppTheme.mono,
          ),
        ),
      ],
    );
  }
}

class _MainContent extends StatelessWidget {
  final ValidationState state;

  const _MainContent({required this.state});

  @override
  Widget build(BuildContext context) {
    final status = state.overallStatus;

    if (status == ValidationStatus.notStarted) {
      return _NotStartedContent(canRun: state.canRun);
    }

    // Running, and we truly have nothing to show a pipeline with yet
    // (first-ever run for this analysis).
    if (status == ValidationStatus.running && state.checks.isEmpty) {
      return const ValidationRunningNotice();
    }

    final isFinal =
        status == ValidationStatus.passed ||
        status == ValidationStatus.failed ||
        status == ValidationStatus.unavailable;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (state.checks.isNotEmpty) ...[
          ValidationChecksHeader(state: state),
          _ChecksList(checks: state.checks),
        ] else if (isFinal)
          const _EmptyChecksContent(),

        // The overall verdict is the conclusion of the pipeline, not
        // its headline — shown last, once there actually is one.
        if (isFinal) ...[
          if (state.checks.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.section),
            const Divider(height: 1, color: AppTheme.border),
          ],
          const SizedBox(height: AppSpacing.section),
          ValidationSummary(state: state),
        ],

        if (state.warnings.isNotEmpty) ...[
          const SizedBox(height: 20),
          _MessageBanner(
            messages: state.warnings,
            color: AppTheme.warning,
            icon: Icons.warning_amber_outlined,
          ),
        ],
        if (state.errorMessage != null &&
            state.errorMessage!.trim().isNotEmpty) ...[
          const SizedBox(height: 20),
          _MessageBanner(
            messages: [state.errorMessage!],
            color: AppTheme.danger,
            icon: Icons.error_outline,
          ),
        ],
        if (state.globalLog != null && state.globalLog!.trim().isNotEmpty) ...[
          const SizedBox(height: 18),
          ValidationLogSection(log: state.globalLog!),
        ],
      ],
    );
  }
}

class _ChecksList extends StatelessWidget {
  final List<ValidationCheck> checks;

  const _ChecksList({required this.checks});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        border: Border(top: BorderSide(color: AppTheme.border, width: 1)),
      ),
      child: Column(
        children: [
          for (final check in checks)
            ValidationCheckTile(
              key: ValueKey(check.id),
              check: check,
              initiallyExpanded:
                  check.status == CheckStatus.failed && check.hasOutput,
            ),
        ],
      ),
    );
  }
}

class _NotStartedContent extends StatelessWidget {
  final bool canRun;

  const _NotStartedContent({required this.canRun});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 18),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            canRun ? Icons.fact_check_outlined : Icons.block_outlined,
            size: 16,
            color: AppTheme.textMuted,
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  canRun ? 'Ready to validate' : 'No patch to validate',
                  style: const TextStyle(
                    color: AppTheme.text,
                    fontSize: 13,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  canRun
                      ? 'Run the validation checks to verify the generated patch.'
                      : 'Generate a patch on the Patch stage, then return here '
                            'to validate it.',
                  style: const TextStyle(
                    color: AppTheme.textMuted,
                    fontSize: 12,
                    height: 1.45,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _EmptyChecksContent extends StatelessWidget {
  const _EmptyChecksContent();

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.symmetric(vertical: 24),
      child: Text(
        'No validation checks are available.',
        style: TextStyle(color: AppTheme.textMuted, fontSize: 13),
      ),
    );
  }
}

class _MessageBanner extends StatelessWidget {
  final List<String> messages;
  final Color color;
  final IconData icon;

  const _MessageBanner({
    required this.messages,
    required this.color,
    required this.icon,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        border: Border.all(color: color.withValues(alpha: 0.28)),
        borderRadius: BorderRadius.circular(AppRadii.sm),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 18, color: color),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              messages.join('\n'),
              style: TextStyle(color: color, fontSize: 12, height: 1.45),
            ),
          ),
        ],
      ),
    );
  }
}

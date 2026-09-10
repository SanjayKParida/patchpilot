import 'package:flutter/material.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/core/widgets/common.dart';
import 'package:patchpilot_web/core/widgets/motion.dart';
import 'package:patchpilot_web/features/repair/code_viewer/widgets/syntax_highlighter.dart';
import 'package:patchpilot_web/features/repair/shell/repair_section_help.dart';
import 'package:patchpilot_web/models/models.dart';
import 'package:patchpilot_web/services/api_client.dart';

import 'patch_diff.dart';

/// Review a generated patch without replacing the diagnosis.
///
/// Generation, validation, approval, and delivery are separate steps.
/// A successful generate is never treated as a working repair.
/// Approval does not open a PR; delivery does.
class PatchPanel extends StatefulWidget {
  final ApiClient api;
  final String analysisId;
  final String? commitSha;
  final String? requestedRef;
  final void Function(String path, {int? line, String? reason}) onOpenFile;
  final void Function(
    PatchProposal? proposal,
    PatchValidationResult? validation,
    PatchApproval? approval,
    PatchDelivery? delivery,
  )?
  onArtifactsChanged;
  final ValueChanged<bool>? onBusyChanged;

  /// When false (Repair workflow Patch stage), hide Validate/Approve/Deliver
  /// so progression is Generate → review diff → Continue to Validation.
  final bool showLifecycleActions;

  const PatchPanel({
    super.key,
    required this.api,
    required this.analysisId,
    required this.onOpenFile,
    this.commitSha,
    this.requestedRef,
    this.onArtifactsChanged,
    this.onBusyChanged,
    this.showLifecycleActions = true,
  });

  @override
  State<PatchPanel> createState() => _PatchPanelState();
}

class _PatchPanelState extends State<PatchPanel> {
  PatchProposal? _proposal;
  PatchValidationResult? _validation;
  PatchApproval? _approval;
  PatchDelivery? _delivery;
  String? _error;
  bool _loadingPatch = false;
  bool _loadingCached = true;
  bool _validating = false;
  bool _approving = false;
  bool _delivering = false;

  bool get _busy =>
      _loadingCached || _loadingPatch || _validating || _approving || _delivering;

  @override
  void initState() {
    super.initState();
    _scheduleNotify();
    _loadCached();
  }

  Future<void> _loadCached() async {
    PatchProposal? proposal;
    PatchValidationResult? validation;
    PatchApproval? approval;
    PatchDelivery? delivery;
    String? error;

    try {
      proposal = await widget.api.getPatch(widget.analysisId);
    } on ApiException catch (e) {
      if (e.statusCode == 409) {
        // Generation is still running; do not treat this as a missing artifact.
      } else if (!_isMissingArtifact(e)) {
        error = e.message;
      }
    }

    if (proposal != null) {
      try {
        validation = await widget.api.getPatchValidation(widget.analysisId);
      } on ApiException catch (e) {
        if (!_isMissingArtifact(e)) error ??= e.message;
      }
    }

    if (validation != null && validation.isPassed) {
      try {
        approval = await widget.api.getPatchApproval(widget.analysisId);
      } on ApiException catch (e) {
        if (!_isMissingArtifact(e)) error ??= e.message;
      }
    }

    if (approval != null && approval.approved) {
      try {
        delivery = await widget.api.getPatchDelivery(widget.analysisId);
      } on ApiException catch (e) {
        if (!_isMissingArtifact(e)) error ??= e.message;
      }
    }

    if (!mounted) return;
    setState(() {
      _proposal = proposal;
      _validation = validation;
      _approval = approval;
      _delivery = delivery;
      _error = error;
      _loadingCached = false;
    });
    _scheduleNotify();
  }

  void _scheduleNotify() {
    final onArtifacts = widget.onArtifactsChanged;
    final onBusy = widget.onBusyChanged;
    if (onArtifacts == null && onBusy == null) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      onArtifacts?.call(_proposal, _validation, _approval, _delivery);
      onBusy?.call(_busy);
    });
  }

  bool _isMissingArtifact(ApiException error) {
    return error.statusCode == 502 || error.statusCode == 404;
  }

  Future<void> _generate() async {
    if (_loadingPatch) return;

    setState(() {
      _loadingPatch = true;
      _error = null;
      _approval = null;
      _delivery = null;
      _validation = null;
    });
    _scheduleNotify();

    try {
      final proposal = await widget.api.generatePatch(widget.analysisId);
      if (!mounted) return;
      setState(() => _proposal = proposal);
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
    } finally {
      if (mounted) {
        setState(() => _loadingPatch = false);
        _scheduleNotify();
      }
    }
  }

  Future<void> _validate() async {
    if (_validating) return;

    setState(() {
      _validating = true;
      _error = null;
      _approval = null;
      _delivery = null;
      _validation = null;
    });
    _scheduleNotify();

    try {
      final result = await widget.api.validatePatch(widget.analysisId);
      if (!mounted) return;
      setState(() => _validation = result);
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
    } finally {
      if (mounted) {
        setState(() => _validating = false);
        _scheduleNotify();
      }
    }
  }

  Future<void> _approve() async {
    if (_approving) return;
    if (_validation?.isPassed != true) return;

    setState(() {
      _approving = true;
      _error = null;
    });
    _scheduleNotify();

    try {
      final approval = await widget.api.approvePatch(widget.analysisId);
      if (!mounted) return;
      setState(() => _approval = approval);
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
    } finally {
      if (mounted) {
        setState(() => _approving = false);
        _scheduleNotify();
      }
    }
  }

  Future<void> _deliver() async {
    if (_delivering) return;
    if (_validation?.isPassed != true) return;
    if (_approval?.approved != true) return;
    if (_delivery?.isSucceeded == true) return;

    setState(() {
      _delivering = true;
      _error = null;
    });
    _scheduleNotify();

    try {
      var result = await widget.api.deliverPatch(widget.analysisId);
      if (!mounted) return;
      setState(() => _delivery = result);
    } on ApiException catch (e) {
      if (!mounted) return;
      if (e.statusCode == 409) {
        try {
          final polled = await _pollDelivery();
          if (!mounted) return;
          if (polled != null) {
            setState(() => _delivery = polled);
          } else {
            setState(() => _error = e.message);
          }
        } on ApiException catch (pollError) {
          if (!mounted) return;
          setState(() => _error = pollError.message);
        }
      } else {
        PatchDelivery? stored;
        try {
          stored = await _loadDeliveryQuietly();
        } on ApiException {
          stored = null;
        }
        if (!mounted) return;
        setState(() {
          if (stored != null) {
            _delivery = stored;
          } else {
            _error = e.message;
          }
        });
      }
    } finally {
      if (mounted) {
        setState(() => _delivering = false);
        _scheduleNotify();
      }
    }
  }

  Future<PatchDelivery?> _pollDelivery() async {
    for (var attempt = 0; attempt < 45; attempt++) {
      final current = await _loadDeliveryQuietly();
      if (current != null && !current.isRunning) return current;
      await Future<void>.delayed(const Duration(milliseconds: 1200));
    }
    return _loadDeliveryQuietly();
  }

  Future<PatchDelivery?> _loadDeliveryQuietly() async {
    try {
      return await widget.api.getPatchDelivery(widget.analysisId);
    } on ApiException catch (e) {
      if (_isMissingArtifact(e)) return null;
      rethrow;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _buildToolbar(),
        if (_error != null) ...[
          const SizedBox(height: 12),
          ErrorNotice(title: 'Patch request failed', message: _error!),
        ],
        const SizedBox(height: 12),
        if (_loadingCached || _loadingPatch)
          Container(
            padding: const EdgeInsets.symmetric(vertical: 48),
            decoration: BoxDecoration(
              color: AppTheme.workspace,
              borderRadius: AppRadii.panel,
              border: Border.all(color: AppTheme.borderSubtle),
            ),
            child: Center(child: AppSpinner(size: 18, color: AppTheme.accent)),
          )
        else if (_proposal == null)
          _buildEmpty()
        else ...[
          _ProposalBody(proposal: _proposal!, onOpenFile: widget.onOpenFile),
          if (widget.showLifecycleActions) ...[
            const SizedBox(height: 20),
            const Divider(height: 1, color: AppTheme.borderSubtle),
            const SizedBox(height: 16),
            _ValidationSection(
              proposal: _proposal!,
              validation: _validation,
              validating: _validating,
              approving: _approving,
              approved: _approval?.approved == true,
              onValidate: _validate,
              onApprove: _approve,
            ),
            if (_validation?.isPassed == true &&
                _approval?.approved == true) ...[
              const SizedBox(height: 20),
              const Divider(height: 1, color: AppTheme.borderSubtle),
              const SizedBox(height: 16),
              _DeliverySection(
                delivery: _delivery,
                delivering: _delivering,
                analyzedCommit: _displayCommit,
                onDeliver: _deliver,
              ),
            ],
          ],
        ],
      ],
    );
  }

  Widget _buildToolbar() {
    final commit = _displayCommit;

    return Row(
      children: [
        Icon(Icons.difference_outlined, size: 16, color: AppTheme.accent),
        const SizedBox(width: 8),
        Flexible(
          child: Row(
            children: [
              Text(
                'Proposed patch',
                style: AppTypography.title.copyWith(fontSize: 14),
              ),
              const SectionInfoButton(message: RepairSectionHelp.proposedPatch),
              if (commit != null) ...[
                const SizedBox(width: 10),
                const Text(
                  '·',
                  style: TextStyle(color: AppTheme.textMuted, fontSize: 12),
                ),
                const SizedBox(width: 10),
                Flexible(
                  child: Tooltip(
                    message: commit,
                    child: Text(
                      'Patching ${_shortSha(commit)}',
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 12,
                        fontFamily: AppTheme.mono,
                        color: AppTheme.textMuted,
                      ),
                    ),
                  ),
                ),
              ],
            ],
          ),
        ),
        if (_proposal == null && !_loadingCached && !_loadingPatch)
          FilledButton(
            onPressed: _generate,
            style: FilledButton.styleFrom(
              backgroundColor: AppTheme.accent,
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            ),
            child: const Text('Generate patch'),
          ),
      ],
    );
  }

  String? get _displayCommit {
    final sha = widget.commitSha?.trim();
    if (sha != null && sha.isNotEmpty) return sha;
    final requested = widget.requestedRef?.trim();
    if (requested != null && requested.isNotEmpty) return requested;
    return null;
  }

  static String _shortSha(String value) {
    if (value.length <= 12) return value;
    return value.substring(0, 12);
  }

  Widget _buildEmpty() {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 40, horizontal: 20),
      decoration: BoxDecoration(
        color: AppTheme.workspace,
        borderRadius: AppRadii.panel,
        border: Border.all(color: AppTheme.borderSubtle),
      ),
      child: const EmptyNotice(
        icon: Icons.difference_outlined,
        title: 'No patch yet',
        message: 'Generate a patch to preview proposed file changes.',
      ),
    );
  }
}

class _ProposalBody extends StatelessWidget {
  final PatchProposal proposal;
  final void Function(String path, {int? line, String? reason}) onOpenFile;

  const _ProposalBody({required this.proposal, required this.onOpenFile});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (proposal.status != 'ok') ...[
          ErrorNotice(
            title: _failureTitle(proposal.status),
            message: _statusExplanation(proposal.status) ?? '',
          ),
          const SizedBox(height: 14),
        ],
        Row(
          children: [
            StatusChip(
              label: _statusLabel(proposal.status),
              color: _statusColor(proposal.status),
            ),
            if (proposal.confidencePercent.isNotEmpty) ...[
              const SizedBox(width: 8),
              StatusChip(
                label: proposal.confidencePercent,
                color: AppTheme.textMuted,
                icon: Icons.insights,
              ),
            ],
            if (proposal.summary.isNotEmpty) ...[
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  proposal.summary,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w500,
                    color: AppTheme.textSecondary,
                  ),
                ),
              ),
            ],
          ],
        ),
        if (proposal.errors.isNotEmpty) ...[
          const SizedBox(height: 12),
          ...proposal.errors.map(
            (message) => _MessageRow(
              icon: Icons.error_outline,
              color: AppTheme.danger,
              message: message,
            ),
          ),
        ],
        if (proposal.warnings.isNotEmpty) ...[
          const SizedBox(height: 8),
          ...proposal.warnings.map(
            (message) => _MessageRow(
              icon: Icons.warning_amber_outlined,
              color: AppTheme.warning,
              message: message,
            ),
          ),
        ],
        if (proposal.files.isNotEmpty) ...[
          const SizedBox(height: 14),
          ...proposal.files.map(
            (file) => _FileDiff(
              file: file,
              onOpen: ({int? line}) =>
                  onOpenFile(file.path, line: line, reason: 'Proposed change'),
            ),
          ),
        ],
      ],
    );
  }

  static String _statusLabel(String status) {
    switch (status) {
      case 'ok':
        return 'Generated';
      case 'insufficient_context':
        return 'Insufficient context';
      case 'ambiguous':
        return 'Ambiguous';
      case 'invalid':
        return 'Invalid proposal';
      case 'empty':
        return 'Empty proposal';
      default:
        return status;
    }
  }

  static Color _statusColor(String status) {
    switch (status) {
      case 'ok':
        return AppTheme.accent;
      case 'insufficient_context':
      case 'ambiguous':
        return AppTheme.warning;
      case 'invalid':
        return AppTheme.danger;
      default:
        return AppTheme.textMuted;
    }
  }

  static String _failureTitle(String status) {
    switch (status) {
      case 'insufficient_context':
        return 'Patch not produced';
      case 'ambiguous':
        return 'Patch ambiguous';
      case 'invalid':
        return 'Patch application failed';
      case 'empty':
        return 'Empty patch';
      default:
        return 'Patch issue';
    }
  }

  static String? _statusExplanation(String status) {
    switch (status) {
      case 'ok':
        return 'Generation succeeded. That is not the same as a working patch.';
      case 'insufficient_context':
        return 'PatchPilot could not safely produce a patch. '
            'The available context was not enough to propose a change.';
      case 'ambiguous':
        return 'The generator was not confident enough to propose a '
            'single repair. The uncertainty is shown above.';
      case 'invalid':
        return 'The proposal failed deterministic checks and should not '
            'be treated as a patch.';
      case 'empty':
        return 'The generator returned no file changes.';
      default:
        return null;
    }
  }
}

class _FileDiff extends StatelessWidget {
  final PatchFile file;
  final void Function({int? line}) onOpen;

  const _FileDiff({required this.file, required this.onOpen});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Container(
        decoration: BoxDecoration(
          color: AppTheme.workspace,
          borderRadius: AppRadii.panel,
          border: Border.all(color: AppTheme.borderSubtle),
        ),
        clipBehavior: Clip.antiAlias,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Material(
              color: AppTheme.chrome,
              child: InkWell(
                onTap: () => onOpen(
                  line: file.hunks.isEmpty ? null : file.hunks.first.startLine,
                ),
                child: Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 8,
                  ),
                  child: Row(
                    children: [
                      const Icon(
                        Icons.insert_drive_file_outlined,
                        size: 14,
                        color: AppTheme.accent,
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          file.path,
                          style: AppTypography.code(
                            fontSize: 12,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      ),
                      Text(
                        '${file.hunks.length} '
                        '${file.hunks.length == 1 ? 'hunk' : 'hunks'}',
                        style: const TextStyle(
                          fontSize: 11,
                          color: AppTheme.textMuted,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
            ...file.hunks.map(
              (hunk) =>
                  _HunkDiff(hunk: hunk, filePath: file.path, onOpen: onOpen),
            ),
          ],
        ),
      ),
    );
  }
}

class _HunkDiff extends StatelessWidget {
  final PatchHunk hunk;
  final String filePath;
  final void Function({int? line}) onOpen;

  const _HunkDiff({
    required this.hunk,
    required this.filePath,
    required this.onOpen,
  });

  static const double _gutterW = 36;
  static const double _markerW = 18;

  @override
  Widget build(BuildContext context) {
    final lines = diffHunkTexts(
      hunk.oldText,
      hunk.newText,
      startLine: hunk.startLine,
    );
    final language = SyntaxHighlighter.languageFromPath(filePath);
    final gutterStyle = AppTypography.code(
      fontSize: 11,
      color: AppTheme.textMuted,
    );
    final codeStyle = AppTypography.code();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Material(
          color: AppTheme.surfaceElevated,
          child: InkWell(
            onTap: () => onOpen(line: hunk.startLine),
            child: Padding(
              padding: const EdgeInsets.fromLTRB(12, 6, 12, 6),
              child: Text(
                '@@ ${hunk.startLine},${hunk.endLine} @@',
                style: AppTypography.code(
                  fontSize: 11,
                  color: AppTheme.textMuted,
                ),
              ),
            ),
          ),
        ),
        DecoratedBox(
          decoration: const BoxDecoration(
            border: Border(top: BorderSide(color: AppTheme.borderSubtle)),
          ),
          child: LayoutBuilder(
            builder: (context, constraints) {
              return SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: ConstrainedBox(
                  constraints: BoxConstraints(minWidth: constraints.maxWidth),
                  child: IntrinsicWidth(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        for (final line in lines)
                          _line(
                            line,
                            language: language,
                            gutterStyle: gutterStyle,
                            codeStyle: codeStyle,
                          ),
                      ],
                    ),
                  ),
                ),
              );
            },
          ),
        ),
      ],
    );
  }

  Widget _line(
    DiffLine line, {
    required String? language,
    required TextStyle gutterStyle,
    required TextStyle codeStyle,
  }) {
    late final Color background;
    late final Color accentBar;
    late final Color markerColor;
    late final String marker;

    switch (line.kind) {
      case DiffKind.added:
        background = const Color(0xFF12261A);
        accentBar = AppTheme.success;
        markerColor = AppTheme.success;
        marker = '+';
      case DiffKind.removed:
        background = const Color(0xFF2A1518);
        accentBar = AppTheme.danger;
        markerColor = AppTheme.danger;
        marker = '-';
      case DiffKind.unchanged:
        background = Colors.transparent;
        accentBar = Colors.transparent;
        markerColor = AppTheme.textMuted;
        marker = ' ';
    }

    final codeSpan = SyntaxHighlighter.highlight(
      source: line.text.isEmpty ? ' ' : line.text,
      language: language,
      baseStyle: codeStyle,
    );

    return Material(
      color: background,
      child: InkWell(
        onTap: () => onOpen(line: line.newLine ?? line.oldLine),
        child: IntrinsicHeight(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Container(width: 3, color: accentBar),
              SizedBox(
                width: _gutterW,
                child: Padding(
                  padding: const EdgeInsets.only(right: 6),
                  child: Align(
                    alignment: Alignment.centerRight,
                    child: Text(
                      line.oldLine?.toString() ?? '',
                      style: gutterStyle,
                    ),
                  ),
                ),
              ),
              SizedBox(
                width: _gutterW,
                child: Padding(
                  padding: const EdgeInsets.only(right: 4),
                  child: Align(
                    alignment: Alignment.centerRight,
                    child: Text(
                      line.newLine?.toString() ?? '',
                      style: gutterStyle,
                    ),
                  ),
                ),
              ),
              SizedBox(
                width: _markerW,
                child: Center(
                  child: Text(
                    marker,
                    style: AppTypography.code(
                      fontSize: 12,
                      color: markerColor,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(0, 1, 12, 1),
                child: Text.rich(
                  codeSpan,
                  softWrap: false,
                  overflow: TextOverflow.visible,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ValidationSection extends StatelessWidget {
  final PatchProposal proposal;
  final PatchValidationResult? validation;
  final bool validating;
  final bool approving;
  final bool approved;
  final VoidCallback onValidate;
  final VoidCallback onApprove;

  const _ValidationSection({
    required this.proposal,
    required this.validation,
    required this.validating,
    required this.approving,
    required this.approved,
    required this.onValidate,
    required this.onApprove,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            _statusChip(),
            const Spacer(),
            if (validating)
              const AppSpinner(size: 16)
            else if (proposal.canValidate)
              FilledButton(
                onPressed: onValidate,
                child: const Text('Validate patch'),
              ),
          ],
        ),
        if (validating) ...[
          const SizedBox(height: 12),
          const Text(
            'Applying the patch to the pinned commit, then running '
            'Flutter checks. This does not create a branch or pull request.',
            style: TextStyle(fontSize: 13, color: AppTheme.textMuted),
          ),
          const SizedBox(height: 12),
          ..._progressSteps(),
        ],
        if (validation != null) ...[
          const SizedBox(height: 12),
          if (validation!.isUnavailable)
            Text(
              validation!.unavailableReason.isEmpty
                  ? 'Validation could not run Flutter checks against '
                        'the pinned repository snapshot.'
                  : 'Validation unavailable: ${validation!.unavailableReason}',
              style: const TextStyle(
                fontSize: 13.5,
                height: 1.5,
                color: AppTheme.warning,
              ),
            ),
          if (validation!.errors.isNotEmpty) ...[
            const SizedBox(height: 8),
            ...validation!.errors.map(
              (message) => _MessageRow(
                icon: Icons.error_outline,
                color: AppTheme.danger,
                message: message,
              ),
            ),
          ],
          if (validation!.warnings.isNotEmpty) ...[
            const SizedBox(height: 8),
            ...validation!.warnings.map(
              (message) => _MessageRow(
                icon: Icons.warning_amber_outlined,
                color: AppTheme.warning,
                message: message,
              ),
            ),
          ],
          const SizedBox(height: 14),
          const Row(
            children: [
              Text(
                'VALIDATION STEPS',
                style: TextStyle(
                  fontSize: 10,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 1,
                  color: AppTheme.textMuted,
                ),
              ),
              SectionInfoButton(message: RepairSectionHelp.validationSteps),
            ],
          ),
          const SizedBox(height: 8),
          _stepRow(
            label: 'Patch applied',
            passed: validation!.applied,
            detail: validation!.applied ? 'applied' : 'apply failed',
          ),
          ...validation!.commands.map(_commandRow),
        ],
        if (validation?.isPassed == true) ...[
          const SizedBox(height: 16),
          if (approved)
            const StatusChip(
              label: 'Patch approved',
              color: AppTheme.success,
              icon: Icons.verified_outlined,
            )
          else if (approving)
            const StatusChip(
              label: 'Approving',
              color: AppTheme.accent,
              icon: Icons.hourglass_top,
            )
          else
            FilledButton(
              onPressed: onApprove,
              style: FilledButton.styleFrom(
                backgroundColor: AppTheme.success,
                padding: const EdgeInsets.symmetric(
                  horizontal: 18,
                  vertical: 16,
                ),
              ),
              child: const Text('Approve patch'),
            ),
          if (approved) ...[
            const SizedBox(height: 8),
            const Text(
              'Approval is stored on the server. '
              'Opening a draft pull request is a separate step.',
              style: TextStyle(fontSize: 12.5, color: AppTheme.textMuted),
            ),
          ],
        ],
      ],
    );
  }

  Widget _statusChip() {
    if (validating) {
      return const StatusChip(
        label: 'Validating',
        color: AppTheme.accent,
        icon: Icons.hourglass_top,
      );
    }

    final result = validation;
    if (result == null) {
      return const StatusChip(
        label: 'Not validated',
        color: AppTheme.textMuted,
      );
    }
    if (result.isPassed) {
      return const StatusChip(
        label: 'Validation passed',
        color: AppTheme.success,
        icon: Icons.check_circle_outline,
      );
    }
    if (result.isUnavailable) {
      return const StatusChip(
        label: 'Validation unavailable',
        color: AppTheme.warning,
        icon: Icons.help_outline,
      );
    }
    return const StatusChip(
      label: 'Validation failed',
      color: AppTheme.danger,
      icon: Icons.error_outline,
    );
  }

  List<Widget> _progressSteps() {
    return const [
      _MessageRow(
        icon: Icons.hourglass_top,
        color: AppTheme.accent,
        message: 'Patch applied — running',
      ),
      _MessageRow(
        icon: Icons.hourglass_empty,
        color: AppTheme.textMuted,
        message: 'flutter pub get',
      ),
      _MessageRow(
        icon: Icons.hourglass_empty,
        color: AppTheme.textMuted,
        message: 'flutter analyze',
      ),
      _MessageRow(
        icon: Icons.hourglass_empty,
        color: AppTheme.textMuted,
        message: 'flutter test',
      ),
    ];
  }

  Widget _stepRow({
    required String label,
    required bool passed,
    required String detail,
  }) {
    final color = passed ? AppTheme.success : AppTheme.danger;
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            passed ? Icons.check_circle_outline : Icons.cancel_outlined,
            size: 16,
            color: color,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  style: TextStyle(
                    fontSize: 13,
                    fontFamily: AppTheme.mono,
                    color: color,
                  ),
                ),
                Text(
                  detail,
                  style: const TextStyle(
                    fontSize: 12,
                    color: AppTheme.textMuted,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _commandRow(ValidationCommandResult command) {
    final color = command.passed ? AppTheme.success : AppTheme.danger;
    final detail = command.timedOut
        ? 'timed out'
        : command.passed && (command.exitCode ?? 0) != 0
        ? 'exit ${command.exitCode} · no new diagnostics'
        : 'exit ${command.exitCode ?? '?'}';

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            command.passed ? Icons.check_circle_outline : Icons.cancel_outlined,
            size: 16,
            color: color,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  command.displayName,
                  style: TextStyle(
                    fontSize: 13,
                    fontFamily: AppTheme.mono,
                    color: color,
                  ),
                ),
                Text(
                  detail,
                  style: const TextStyle(
                    fontSize: 12,
                    color: AppTheme.textMuted,
                  ),
                ),
                if (!command.passed && command.stderr.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: Text(
                      command.stderr,
                      maxLines: 6,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 12,
                        fontFamily: AppTheme.mono,
                        color: AppTheme.textMuted,
                        height: 1.4,
                      ),
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

class _DeliverySection extends StatelessWidget {
  final PatchDelivery? delivery;
  final bool delivering;
  final String? analyzedCommit;
  final VoidCallback onDeliver;

  const _DeliverySection({
    required this.delivery,
    required this.delivering,
    required this.analyzedCommit,
    required this.onDeliver,
  });

  @override
  Widget build(BuildContext context) {
    final result = delivery;
    final succeeded = result?.isSucceeded == true;
    final failed = result?.isFailed == true;
    final showRetry = failed && !delivering && !succeeded;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            _statusChip(),
            const Spacer(),
            if (delivering)
              const AppSpinner(size: 16)
            else if (!succeeded)
              FilledButton(
                onPressed: onDeliver,
                style: FilledButton.styleFrom(
                  backgroundColor: AppTheme.accent,
                  padding: const EdgeInsets.symmetric(
                    horizontal: 18,
                    vertical: 16,
                  ),
                ),
                child: Text(showRetry ? 'Retry draft PR' : 'Create draft PR'),
              ),
          ],
        ),
        if (analyzedCommit != null && analyzedCommit!.isNotEmpty) ...[
          const SizedBox(height: 12),
          Tooltip(
            message: analyzedCommit!,
            child: Text(
              'Patching ${_shortSha(analyzedCommit!)}',
              style: const TextStyle(
                fontSize: 12.5,
                fontFamily: AppTheme.mono,
                color: AppTheme.accent,
              ),
            ),
          ),
        ],
        if (delivering) ...[
          const SizedBox(height: 12),
          const Text(
            'Creating a branch from the analyzed commit and opening a '
            'draft pull request. This does not merge.',
            style: TextStyle(fontSize: 13, color: AppTheme.textMuted),
          ),
          const SizedBox(height: 12),
          ..._progressSteps(result?.stage),
        ],
        if (result != null && !delivering) ...[
          const SizedBox(height: 12),
          Text(
            'Stage: ${result.stageLabel}',
            style: TextStyle(
              fontSize: 13,
              fontFamily: AppTheme.mono,
              color: failed ? AppTheme.danger : AppTheme.textMuted,
            ),
          ),
          if (result.branch != null && result.branch!.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(
              result.branch!,
              style: const TextStyle(fontSize: 13, fontFamily: AppTheme.mono),
            ),
          ],
          if (result.commitSha != null && result.commitSha!.isNotEmpty) ...[
            const SizedBox(height: 6),
            Tooltip(
              message: result.commitSha!,
              child: Text(
                'Commit ${result.shortCommit}',
                style: const TextStyle(
                  fontSize: 12.5,
                  fontFamily: AppTheme.mono,
                  color: AppTheme.textMuted,
                ),
              ),
            ),
          ],
          if (result.prNumber != null) ...[
            const SizedBox(height: 8),
            Text(
              'Pull request #${result.prNumber}'
              '${result.draft ? ' (draft)' : ''}',
              style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
            ),
          ],
          if (result.prUrl != null && result.prUrl!.isNotEmpty) ...[
            const SizedBox(height: 6),
            SelectableText(
              result.prUrl!,
              style: const TextStyle(
                fontSize: 13,
                fontFamily: AppTheme.mono,
                color: AppTheme.accent,
              ),
            ),
          ],
          if (result.errors.isNotEmpty) ...[
            const SizedBox(height: 10),
            ...result.errors.map(
              (message) => _MessageRow(
                icon: Icons.error_outline,
                color: AppTheme.danger,
                message: message,
              ),
            ),
          ],
          if (result.warnings.isNotEmpty) ...[
            const SizedBox(height: 8),
            ...result.warnings.map(
              (message) => _MessageRow(
                icon: Icons.warning_amber_outlined,
                color: AppTheme.warning,
                message: message,
              ),
            ),
          ],
        ],
      ],
    );
  }

  Widget _statusChip() {
    if (delivering) {
      return const StatusChip(
        label: 'Opening draft PR',
        color: AppTheme.accent,
        icon: Icons.hourglass_top,
      );
    }

    final result = delivery;
    if (result == null) {
      return const StatusChip(
        label: 'Not delivered',
        color: AppTheme.textMuted,
      );
    }
    if (result.isSucceeded) {
      return const StatusChip(
        label: 'Draft PR opened',
        color: AppTheme.success,
        icon: Icons.merge_type,
      );
    }
    if (result.isRunning) {
      return const StatusChip(
        label: 'Delivery running',
        color: AppTheme.accent,
        icon: Icons.hourglass_top,
      );
    }
    return StatusChip(
      label: 'Delivery failed (${result.stageLabel})',
      color: AppTheme.danger,
      icon: Icons.error_outline,
    );
  }

  List<Widget> _progressSteps(String? stage) {
    const stages = [
      ('apply', 'Apply patch'),
      ('commit', 'Create commit'),
      ('push', 'Push branch'),
      ('pull_request', 'Open pull request'),
    ];
    return [
      for (final item in stages)
        _MessageRow(
          icon: item.$1 == stage ? Icons.hourglass_top : Icons.hourglass_empty,
          color: item.$1 == stage ? AppTheme.accent : AppTheme.textMuted,
          message: item.$2,
        ),
    ];
  }

  static String _shortSha(String value) {
    if (value.length <= 12) return value;
    return value.substring(0, 12);
  }
}

class _MessageRow extends StatelessWidget {
  final IconData icon;
  final Color color;
  final String message;

  const _MessageRow({
    required this.icon,
    required this.color,
    required this.message,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 16, color: color),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              message,
              style: TextStyle(fontSize: 13.5, height: 1.45, color: color),
            ),
          ),
        ],
      ),
    );
  }
}

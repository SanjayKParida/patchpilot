// validation_widgets.dart
import 'package:flutter/material.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/core/widgets/common.dart';
import 'package:patchpilot_web/features/repair/shell/repair_section_help.dart';

import 'validation_models.dart';

/// A small looping-opacity dot used as the "something is happening"
/// signal in place of a circular spinner. Intentionally minimal —
/// it communicates activity without claiming to represent progress
/// through any particular step.
class ValidationPulseDot extends StatefulWidget {
  const ValidationPulseDot({super.key, this.size = 8, this.color});

  final double size;
  final Color? color;

  @override
  State<ValidationPulseDot> createState() => _ValidationPulseDotState();
}

class _ValidationPulseDotState extends State<ValidationPulseDot>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1100),
  )..repeat(reverse: true);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: Tween<double>(
        begin: 0.3,
        end: 1,
      ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeInOut)),
      child: Container(
        width: widget.size,
        height: widget.size,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: widget.color ?? AppTheme.accent,
        ),
      ),
    );
  }
}

/// Shown while a validation run is in flight but we have no prior
/// result for this analysis to shape a pipeline preview from — the
/// only honest thing to say is that it's running and what will
/// appear once it finishes. No placeholder boxes, no step list.
class ValidationRunningNotice extends StatelessWidget {
  const ValidationRunningNotice({super.key});

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.symmetric(vertical: 18),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: EdgeInsets.only(top: 4),
            child: ValidationPulseDot(size: 8),
          ),
          SizedBox(width: 12),
          Expanded(
            child: Text(
              'Applying the patch and running Flutter checks. Step-by-step '
              'results will appear here once validation finishes.',
              style: TextStyle(
                color: AppTheme.textMuted,
                fontSize: 12.5,
                height: 1.5,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class ValidationStatusIcon extends StatelessWidget {
  final ValidationStatus status;
  final double size;

  const ValidationStatusIcon({super.key, required this.status, this.size = 20});

  @override
  Widget build(BuildContext context) {
    switch (status) {
      case ValidationStatus.notStarted:
        return Icon(
          Icons.radio_button_unchecked,
          size: size,
          color: AppTheme.textMuted,
        );

      case ValidationStatus.running:
        return SizedBox(
          width: size,
          height: size,
          child: Center(
            child: ValidationPulseDot(
              size: size * 0.45,
              color: AppTheme.accent,
            ),
          ),
        );

      case ValidationStatus.passed:
        return Icon(
          Icons.check_circle_outline,
          size: size,
          color: AppTheme.success,
        );

      case ValidationStatus.failed:
        return Icon(Icons.error_outline, size: size, color: AppTheme.danger);

      case ValidationStatus.unavailable:
        return Icon(Icons.help_outline, size: size, color: AppTheme.warning);
    }
  }
}

class CheckStatusIcon extends StatelessWidget {
  final CheckStatus status;
  final double size;

  const CheckStatusIcon({super.key, required this.status, this.size = 18});

  @override
  Widget build(BuildContext context) {
    switch (status) {
      case CheckStatus.pending:
        return Icon(
          Icons.circle_outlined,
          size: size,
          color: AppTheme.textMuted,
        );

      case CheckStatus.running:
        return SizedBox(
          width: size,
          height: size,
          child: Center(
            child: ValidationPulseDot(
              size: size * 0.45,
              color: AppTheme.accent,
            ),
          ),
        );

      case CheckStatus.passed:
        return Icon(
          Icons.check_circle_outline,
          size: size,
          color: AppTheme.success,
        );

      case CheckStatus.failed:
        return Icon(Icons.cancel_outlined, size: size, color: AppTheme.danger);
    }
  }
}

class ValidationCheckTile extends StatefulWidget {
  final ValidationCheck check;
  final bool initiallyExpanded;

  const ValidationCheckTile({
    super.key,
    required this.check,
    this.initiallyExpanded = false,
  });

  @override
  State<ValidationCheckTile> createState() => _ValidationCheckTileState();
}

class _ValidationCheckTileState extends State<ValidationCheckTile> {
  bool _expanded = false;

  @override
  void initState() {
    super.initState();
    _expanded = widget.initiallyExpanded && widget.check.hasOutput;
  }

  @override
  void didUpdateWidget(covariant ValidationCheckTile oldWidget) {
    super.didUpdateWidget(oldWidget);

    if (!oldWidget.check.hasOutput && widget.check.hasOutput) {
      _expanded = widget.check.status == CheckStatus.failed;
    }
  }

  @override
  Widget build(BuildContext context) {
    final check = widget.check;
    final canExpand = check.hasOutput;

    // Visual weight follows status: failed is the loudest thing in the
    // list, passed steps recede once they're done, pending steps are
    // quietly waiting their turn.
    final isPending = check.status == CheckStatus.pending;
    final isFailed = check.status == CheckStatus.failed;

    final labelColor = isFailed ? AppTheme.text : AppTheme.textMuted;
    final labelWeight = isFailed ? FontWeight.w600 : FontWeight.w500;

    Widget row = Padding(
      padding: const EdgeInsets.symmetric(vertical: 14),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 1),
            child: CheckStatusIcon(status: check.status, size: 16),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  check.label,
                  style: TextStyle(
                    color: labelColor,
                    fontSize: 13.5,
                    fontWeight: labelWeight,
                  ),
                ),
                if (check.detail != null &&
                    check.detail!.trim().isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(
                    check.detail!,
                    style: const TextStyle(
                      color: AppTheme.textMuted,
                      fontSize: 11.5,
                      height: 1.4,
                      fontFamily: AppTheme.mono,
                    ),
                  ),
                ],
                if (check.error != null && check.error!.trim().isNotEmpty) ...[
                  const SizedBox(height: 6),
                  Text(
                    check.error!,
                    maxLines: 3,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: AppTheme.danger,
                      fontSize: 12,
                      height: 1.4,
                      fontFamily: AppTheme.mono,
                    ),
                  ),
                ],
              ],
            ),
          ),
          if (canExpand) ...[
            const SizedBox(width: 12),
            Icon(
              _expanded ? Icons.keyboard_arrow_up : Icons.keyboard_arrow_down,
              size: 18,
              color: AppTheme.textMuted,
            ),
          ],
        ],
      ),
    );

    if (isPending) {
      row = Opacity(opacity: 0.55, child: row);
    }

    return Column(
      children: [
        InkWell(
          onTap: canExpand
              ? () {
                  setState(() {
                    _expanded = !_expanded;
                  });
                }
              : null,
          child: row,
        ),
        if (_expanded && canExpand)
          _ValidationOutput(log: check.log, error: check.error),
        Divider(
          height: 1,
          thickness: 1,
          color: AppTheme.border.withValues(alpha: isPending ? 0.45 : 1),
        ),
      ],
    );
  }
}

class _ValidationOutput extends StatelessWidget {
  final String? log;
  final String? error;

  const _ValidationOutput({this.log, this.error});

  @override
  Widget build(BuildContext context) {
    final output = [
      if (error != null && error!.isNotEmpty) error!,
      if (log != null && log!.isNotEmpty) log!,
    ].join('\n\n');

    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(left: 30, right: 4, bottom: 14),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppTheme.workspace,
        border: Border.all(color: AppTheme.borderSubtle),
        borderRadius: BorderRadius.circular(AppRadii.sm),
      ),
      child: SelectableText(
        output,
        style: AppTypography.code(
          fontSize: 11.5,
          color: AppTheme.textSecondary,
        ),
      ),
    );
  }
}

class ValidationSummary extends StatelessWidget {
  final ValidationState state;

  const ValidationSummary({super.key, required this.state});

  @override
  Widget build(BuildContext context) {
    final status = state.overallStatus;

    String title;
    String description;

    switch (status) {
      case ValidationStatus.notStarted:
        title = 'Validation has not started';
        description = state.canRun
            ? 'Run the validation checks to verify the generated patch.'
            : 'Generate a patch on the Patch stage, then return here '
                  'to validate it.';
        break;

      case ValidationStatus.running:
        title = 'Validating generated patch';
        description = state.checks.isEmpty
            ? 'Applying the patch to the pinned commit, then running '
                  'Flutter checks.'
            : 'Running ${state.checks.length} checks against the pinned '
                  'commit.';
        break;

      case ValidationStatus.passed:
        title = 'Validation passed';
        description =
            state.summary ??
            'The generated patch passed the available validation checks.';
        break;

      case ValidationStatus.failed:
        title = 'Validation failed';
        description =
            state.summary ??
            '${state.failedChecks} validation '
                '${state.failedChecks == 1 ? 'check' : 'checks'} failed.';
        break;

      case ValidationStatus.unavailable:
        title = 'Validation unavailable';
        description =
            state.summary ??
            'Validation could not run Flutter checks against the '
                'pinned repository snapshot.';
        break;
    }

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ValidationStatusIcon(status: status, size: 22),
        const SizedBox(width: 14),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: const TextStyle(
                  color: AppTheme.text,
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                  height: 1.25,
                ),
              ),
              const SizedBox(height: 5),
              Text(
                description,
                style: const TextStyle(
                  color: AppTheme.textMuted,
                  fontSize: 13,
                  height: 1.45,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class ValidationChecksHeader extends StatelessWidget {
  final ValidationState state;

  const ValidationChecksHeader({super.key, required this.state});

  @override
  Widget build(BuildContext context) {
    final status = state.overallStatus;

    String? trailing;
    if (status == ValidationStatus.running) {
      // Honest label, not a fabricated progress count — we don't know
      // how far along the run is.
      trailing = 'running…';
    } else if (status == ValidationStatus.passed ||
        status == ValidationStatus.failed ||
        status == ValidationStatus.unavailable) {
      trailing = '${state.passedChecks}/${state.checks.length} passed';
    }

    return SectionTitle(
      'Validation checks',
      trailing: trailing,
      info: RepairSectionHelp.validationChecks,
    );
  }
}

class ValidationLogSection extends StatefulWidget {
  final String log;

  const ValidationLogSection({super.key, required this.log});

  @override
  State<ValidationLogSection> createState() => _ValidationLogSectionState();
}

class _ValidationLogSectionState extends State<ValidationLogSection> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        InkWell(
          onTap: () {
            setState(() {
              _expanded = !_expanded;
            });
          },
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 12),
            child: Row(
              children: [
                Icon(
                  _expanded
                      ? Icons.keyboard_arrow_up
                      : Icons.keyboard_arrow_down,
                  size: 17,
                  color: AppTheme.textMuted,
                ),
                const SizedBox(width: 8),
                const Text(
                  'Full validation log',
                  style: TextStyle(
                    color: AppTheme.textMuted,
                    fontSize: 12,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ],
            ),
          ),
        ),
        if (_expanded)
          Container(
            width: double.infinity,
            constraints: const BoxConstraints(maxHeight: 320),
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppTheme.surfaceAlt,
              border: Border.all(color: AppTheme.border),
              borderRadius: BorderRadius.circular(AppRadii.sm),
            ),
            child: SingleChildScrollView(
              child: SelectableText(
                widget.log,
                style: AppTypography.code(
                  fontSize: 11,
                  color: AppTheme.textMuted,
                  height: 1.6,
                ),
              ),
            ),
          ),
      ],
    );
  }
}

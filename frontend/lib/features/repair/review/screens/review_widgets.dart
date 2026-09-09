import 'package:flutter/material.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/core/widgets/common.dart';
import 'package:patchpilot_web/features/repair/shell/repair_section_help.dart';

import 'review_models.dart';

class ReviewStatusIndicator extends StatelessWidget {
  final ReviewStatus status;

  const ReviewStatusIndicator({super.key, required this.status});

  @override
  Widget build(BuildContext context) {
    late final IconData icon;
    late final Color color;
    late final String label;

    switch (status) {
      case ReviewStatus.waiting:
        icon = Icons.hourglass_empty_rounded;
        color = AppTheme.textMuted;
        label = 'Waiting for validation';

      case ReviewStatus.ready:
        icon = Icons.check_circle_outline_rounded;
        color = AppTheme.success;
        label = 'Ready for review';

      case ReviewStatus.changesRequested:
        icon = Icons.edit_outlined;
        color = AppTheme.warning;
        label = 'Changes requested';

      case ReviewStatus.approved:
        icon = Icons.verified_outlined;
        color = AppTheme.accent;
        label = 'Approved';
    }

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 17, color: color),
        const SizedBox(width: 7),
        Text(
          label,
          style: TextStyle(
            color: color,
            fontSize: 12,
            fontWeight: FontWeight.w500,
          ),
        ),
      ],
    );
  }
}

class ReviewSectionLabel extends StatelessWidget {
  final String label;
  final String? info;

  const ReviewSectionLabel({super.key, required this.label, this.info});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(label.toUpperCase(), style: AppTypography.sectionLabel),
        if (info != null) SectionInfoButton(message: info!),
      ],
    );
  }
}

class ReviewSummarySection extends StatelessWidget {
  final String rootCause;
  final String patchDescription;

  const ReviewSummarySection({
    super.key,
    required this.rootCause,
    required this.patchDescription,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const ReviewSectionLabel(
          label: 'What changed',
          info: RepairSectionHelp.whatChanged,
        ),
        const SizedBox(height: 14),
        if (rootCause.trim().isNotEmpty) ...[
          const Text(
            'Root cause',
            style: TextStyle(
              color: AppTheme.textMuted,
              fontSize: 12,
              fontWeight: FontWeight.w500,
            ),
          ),
          const SizedBox(height: 5),
          Text(
            rootCause,
            style: const TextStyle(
              color: AppTheme.textSecondary,
              fontSize: 13,
              height: 1.45,
            ),
          ),
        ],
        if (rootCause.trim().isNotEmpty && patchDescription.trim().isNotEmpty)
          const SizedBox(height: 18),
        if (patchDescription.trim().isNotEmpty) ...[
          const Text(
            'Patch',
            style: TextStyle(
              color: AppTheme.textMuted,
              fontSize: 12,
              fontWeight: FontWeight.w500,
            ),
          ),
          const SizedBox(height: 5),
          Text(
            patchDescription,
            style: const TextStyle(
              color: AppTheme.textSecondary,
              fontSize: 12.5,
              height: 1.45,
            ),
          ),
        ],
        if (rootCause.trim().isEmpty && patchDescription.trim().isEmpty)
          const Text(
            'No patch summary is available.',
            style: TextStyle(color: AppTheme.textMuted, fontSize: 13),
          ),
      ],
    );
  }
}

class ChangedFilesSection extends StatelessWidget {
  final List<ChangedFile> files;
  final ValueChanged<ChangedFile>? onFileTap;

  const ChangedFilesSection({super.key, required this.files, this.onFileTap});

  @override
  Widget build(BuildContext context) {
    if (files.isEmpty) {
      return const SizedBox.shrink();
    }

    final additions = files.fold<int>(
      0,
      (total, file) => total + file.additions,
    );

    final deletions = files.fold<int>(
      0,
      (total, file) => total + file.deletions,
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const ReviewSectionLabel(
              label: 'Changed files',
              info: RepairSectionHelp.changedFiles,
            ),
            const Spacer(),
            Text(
              '${files.length} ${files.length == 1 ? 'file' : 'files'}',
              style: const TextStyle(
                fontFamily: AppTheme.mono,
                color: AppTheme.textMuted,
                fontSize: 10,
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        _ChangeTotals(additions: additions, deletions: deletions),
        const SizedBox(height: 10),
        Container(
          decoration: const BoxDecoration(
            border: Border(
              top: BorderSide(color: AppTheme.border),
              bottom: BorderSide(color: AppTheme.border),
            ),
          ),
          child: Column(
            children: [
              for (final file in files)
                ChangedFileRow(
                  file: file,
                  onTap: onFileTap == null ? null : () => onFileTap!(file),
                ),
            ],
          ),
        ),
      ],
    );
  }
}

class _ChangeTotals extends StatelessWidget {
  final int additions;
  final int deletions;

  const _ChangeTotals({required this.additions, required this.deletions});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        if (additions > 0)
          Text(
            '+$additions',
            style: const TextStyle(
              fontFamily: AppTheme.mono,
              color: AppTheme.success,
              fontSize: 11,
            ),
          ),
        if (additions > 0 && deletions > 0) const SizedBox(width: 10),
        if (deletions > 0)
          Text(
            '-$deletions',
            style: const TextStyle(
              fontFamily: AppTheme.mono,
              color: AppTheme.danger,
              fontSize: 11,
            ),
          ),
      ],
    );
  }
}

class ChangedFileRow extends StatelessWidget {
  final ChangedFile file;
  final VoidCallback? onTap;

  const ChangedFileRow({super.key, required this.file, this.onTap});

  @override
  Widget build(BuildContext context) {
    final child = Padding(
      padding: const EdgeInsets.symmetric(vertical: 12),
      child: Row(
        children: [
          const Icon(
            Icons.description_outlined,
            size: 16,
            color: AppTheme.textMuted,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              file.path,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                fontFamily: AppTheme.mono,
                color: AppTheme.text,
                fontSize: 12,
              ),
            ),
          ),
          const SizedBox(width: 16),
          if (file.additions > 0)
            Text(
              '+${file.additions}',
              style: const TextStyle(
                fontFamily: AppTheme.mono,
                color: AppTheme.success,
                fontSize: 10,
              ),
            ),
          if (file.additions > 0 && file.deletions > 0)
            const SizedBox(width: 8),
          if (file.deletions > 0)
            Text(
              '-${file.deletions}',
              style: const TextStyle(
                fontFamily: AppTheme.mono,
                color: AppTheme.danger,
                fontSize: 10,
              ),
            ),
          if (onTap != null) ...[
            const SizedBox(width: 8),
            const Icon(
              Icons.chevron_right_rounded,
              size: 17,
              color: AppTheme.textMuted,
            ),
          ],
        ],
      ),
    );

    if (onTap == null) {
      return child;
    }

    return InkWell(onTap: onTap, child: child);
  }
}

class ValidationResultSection extends StatelessWidget {
  final bool? passed;
  final List<String> warnings;

  const ValidationResultSection({
    super.key,
    required this.passed,
    required this.warnings,
  });

  @override
  Widget build(BuildContext context) {
    if (passed == null) {
      return const Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ReviewSectionLabel(
            label: 'Validation',
            info: RepairSectionHelp.reviewValidation,
          ),
          SizedBox(height: 12),
          Text(
            'Validation result is not available yet.',
            style: TextStyle(color: AppTheme.textMuted, fontSize: 13),
          ),
        ],
      );
    }

    final resultColor = passed! ? AppTheme.success : AppTheme.danger;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const ReviewSectionLabel(
          label: 'Validation',
          info: RepairSectionHelp.reviewValidation,
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Icon(
              passed!
                  ? Icons.check_circle_outline_rounded
                  : Icons.error_outline_rounded,
              size: 18,
              color: resultColor,
            ),
            const SizedBox(width: 9),
            Text(
              passed! ? 'Validation passed' : 'Validation failed',
              style: TextStyle(
                color: resultColor,
                fontSize: 13,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
        if (warnings.isNotEmpty) ...[
          const SizedBox(height: 12),
          for (final warning in warnings)
            Padding(
              padding: const EdgeInsets.only(bottom: 7),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(
                    Icons.warning_amber_outlined,
                    size: 15,
                    color: AppTheme.warning,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      warning,
                      style: const TextStyle(
                        color: AppTheme.warning,
                        fontSize: 12,
                        height: 1.4,
                      ),
                    ),
                  ),
                ],
              ),
            ),
        ],
      ],
    );
  }
}

class ReviewNotesSection extends StatelessWidget {
  final List<String> notes;

  const ReviewNotesSection({super.key, required this.notes});

  @override
  Widget build(BuildContext context) {
    if (notes.isEmpty) {
      return const SizedBox.shrink();
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const ReviewSectionLabel(
          label: 'Notes & limitations',
          info: RepairSectionHelp.notes,
        ),
        const SizedBox(height: 12),
        for (final note in notes)
          Padding(
            padding: const EdgeInsets.only(bottom: 9),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Padding(
                  padding: EdgeInsets.only(top: 5),
                  child: SizedBox(
                    width: 4,
                    height: 4,
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        color: AppTheme.textMuted,
                        shape: BoxShape.circle,
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    note,
                    style: const TextStyle(
                      color: AppTheme.textMuted,
                      fontSize: 12,
                      height: 1.45,
                    ),
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

class ReviewDecisionBar extends StatelessWidget {
  final bool enabled;
  final VoidCallback onApprove;
  final VoidCallback onRequestChanges;

  const ReviewDecisionBar({
    super.key,
    required this.enabled,
    required this.onApprove,
    required this.onRequestChanges,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.only(top: 18),
      decoration: const BoxDecoration(
        border: Border(top: BorderSide(color: AppTheme.border)),
      ),
      child: Row(
        children: [
          Expanded(
            child: FilledButton(
              onPressed: enabled ? onRequestChanges : null,
              style: FilledButton.styleFrom(
                backgroundColor: AppTheme.surfaceElevated,
                foregroundColor: AppTheme.text,
                disabledBackgroundColor: AppTheme.surfaceAlt,
                disabledForegroundColor: AppTheme.textMuted,
                elevation: 0,
                padding: const EdgeInsets.symmetric(
                  vertical: 12,
                  horizontal: 16,
                ),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(AppRadii.sm),
                ),
              ),
              child: const Text(
                'Request changes',
                style: TextStyle(fontSize: 12, fontWeight: FontWeight.w500),
              ),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: FilledButton(
              onPressed: enabled ? onApprove : null,
              style: FilledButton.styleFrom(
                foregroundColor: Colors.white,
                backgroundColor: AppTheme.accent,
                disabledForegroundColor: AppTheme.textMuted,
                disabledBackgroundColor: AppTheme.surfaceAlt,
                elevation: 0,
                padding: const EdgeInsets.symmetric(
                  vertical: 12,
                  horizontal: 16,
                ),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(AppRadii.sm),
                ),
              ),
              child: const Text(
                'Approve patch',
                style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class RequestChangesDialog extends StatefulWidget {
  final ValueChanged<String> onSubmit;

  const RequestChangesDialog({super.key, required this.onSubmit});

  @override
  State<RequestChangesDialog> createState() => _RequestChangesDialogState();
}

class _RequestChangesDialogState extends State<RequestChangesDialog> {
  final TextEditingController _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      backgroundColor: AppTheme.surface,
      title: const Text(
        'Request changes',
        style: TextStyle(
          color: AppTheme.text,
          fontSize: 16,
          fontWeight: FontWeight.w600,
        ),
      ),
      content: SizedBox(
        width: 460,
        child: TextField(
          controller: _controller,
          autofocus: true,
          minLines: 4,
          maxLines: 8,
          style: const TextStyle(
            color: AppTheme.text,
            fontSize: 13,
            height: 1.45,
          ),
          decoration: const InputDecoration(
            hintText: 'Describe what should be changed...',
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () {
            final feedback = _controller.text.trim();
            if (feedback.isEmpty) return;
            Navigator.of(context).pop();
            widget.onSubmit(feedback);
          },
          child: const Text('Request changes'),
        ),
      ],
    );
  }
}

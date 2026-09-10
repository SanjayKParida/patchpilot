import 'package:flutter/material.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/core/widgets/common.dart';
import 'package:patchpilot_web/features/repair/shell/repair_section_help.dart';

import 'pull_request_models.dart';

class PullRequestStatusIndicator extends StatelessWidget {
  final PullRequestStatus status;

  const PullRequestStatusIndicator({super.key, required this.status});

  @override
  Widget build(BuildContext context) {
    late final String label;
    late final IconData icon;
    late final Color color;

    switch (status) {
      case PullRequestStatus.ready:
        label = 'Ready to create';
        icon = Icons.check_circle_outline;
        color = AppTheme.success;
      case PullRequestStatus.creating:
        label = 'Creating';
        icon = Icons.hourglass_empty;
        color = AppTheme.accent;
      case PullRequestStatus.created:
        label = 'Created';
        icon = Icons.check_circle_outline;
        color = AppTheme.success;
      case PullRequestStatus.failed:
        label = 'Failed';
        icon = Icons.error_outline;
        color = AppTheme.danger;
    }

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 15, color: color),
        const SizedBox(width: 6),
        Text(
          label,
          style: TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.w500,
            color: color,
          ),
        ),
      ],
    );
  }
}

class PullRequestSectionLabel extends StatelessWidget {
  final String text;
  final String? info;

  const PullRequestSectionLabel(this.text, {super.key, this.info});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(text.toUpperCase(), style: AppTypography.sectionLabel),
        if (info != null) SectionInfoButton(message: info!),
      ],
    );
  }
}

class PullRequestMetadata extends StatelessWidget {
  final String repository;
  final String baseBranch;
  final String headBranch;
  final int filesChanged;
  final bool? validationPassed;
  final bool? reviewApproved;

  const PullRequestMetadata({
    super.key,
    required this.repository,
    required this.baseBranch,
    required this.headBranch,
    required this.filesChanged,
    required this.validationPassed,
    required this.reviewApproved,
  });

  String _validationText() {
    if (validationPassed == true) return 'Passed';
    if (validationPassed == false) return 'Failed';
    return 'Not completed';
  }

  String _reviewText() {
    if (reviewApproved == true) return 'Approved';
    if (reviewApproved == false) return 'Changes requested';
    return 'Not approved';
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        _row('Repository', repository.isEmpty ? '—' : repository),
        _divider(),
        _row('Base branch', baseBranch.isEmpty ? '—' : baseBranch),
        _divider(),
        _row('Head branch', headBranch.isEmpty ? '—' : headBranch),
        _divider(),
        _row('Files changed', '$filesChanged'),
        _divider(),
        _row('Validation', _validationText()),
        _divider(),
        _row('Review', _reviewText()),
      ],
    );
  }

  Widget _row(String label, String value) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 120,
          child: Text(
            label,
            style: const TextStyle(color: AppTheme.textMuted, fontSize: 12),
          ),
        ),
        Expanded(
          child: Text(
            value,
            style: const TextStyle(
              fontSize: 13,
              fontFamily: AppTheme.mono,
              color: AppTheme.text,
            ),
          ),
        ),
      ],
    );
  }

  Widget _divider() {
    return const Divider(height: 16, color: AppTheme.border);
  }
}

class PullRequestField extends StatelessWidget {
  final String label;
  final String hint;
  final TextEditingController controller;
  final bool enabled;
  final int maxLines;

  const PullRequestField({
    super.key,
    required this.label,
    required this.hint,
    required this.controller,
    required this.enabled,
    this.maxLines = 1,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        PullRequestSectionLabel(label),
        const SizedBox(height: 8),
        TextField(
          controller: controller,
          enabled: enabled,
          maxLines: maxLines,
          style: const TextStyle(fontSize: 13, color: AppTheme.text),
          decoration: InputDecoration(
            hintText: hint,
            filled: true,
            fillColor: AppTheme.surfaceAlt,
            contentPadding: const EdgeInsets.symmetric(
              horizontal: 12,
              vertical: 10,
            ),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(AppRadii.sm),
              borderSide: const BorderSide(color: AppTheme.border),
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(AppRadii.sm),
              borderSide: const BorderSide(color: AppTheme.border),
            ),
            disabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(AppRadii.sm),
              borderSide: const BorderSide(color: AppTheme.border),
            ),
          ),
        ),
      ],
    );
  }
}

class PullRequestPrerequisites extends StatelessWidget {
  final bool? validationPassed;
  final bool? reviewApproved;

  const PullRequestPrerequisites({
    super.key,
    required this.validationPassed,
    required this.reviewApproved,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const PullRequestSectionLabel(
          'Prerequisites',
          info: RepairSectionHelp.prerequisites,
        ),
        const SizedBox(height: 10),
        _item(
          'Validation',
          validationPassed == true
              ? 'Passed'
              : validationPassed == false
              ? 'Failed'
              : 'Not completed',
          validationPassed == true,
        ),
        const SizedBox(height: 8),
        _item(
          'Review',
          reviewApproved == true
              ? 'Approved'
              : reviewApproved == false
              ? 'Changes requested'
              : 'Not approved',
          reviewApproved == true,
        ),
      ],
    );
  }

  Widget _item(String label, String value, bool passed) {
    return Row(
      children: [
        Icon(
          passed ? Icons.check_circle_outline : Icons.radio_button_unchecked,
          size: 16,
          color: passed ? AppTheme.success : AppTheme.textMuted,
        ),
        const SizedBox(width: 8),
        Text(label, style: const TextStyle(color: AppTheme.text, fontSize: 13)),
        const Spacer(),
        Text(
          value,
          style: const TextStyle(color: AppTheme.textMuted, fontSize: 12),
        ),
      ],
    );
  }
}

class PullRequestCreatedView extends StatelessWidget {
  final PullRequestState state;
  final VoidCallback? onViewPr;
  final VoidCallback? onReturnToIssues;

  const PullRequestCreatedView({
    super.key,
    required this.state,
    this.onViewPr,
    this.onReturnToIssues,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Icon(
              Icons.check_circle_outline,
              size: 20,
              color: AppTheme.success,
            ),
            const SizedBox(width: 10),
            Text(
              state.prNumber != null
                  ? 'Pull request #${state.prNumber} created'
                  : 'Pull request created',
              style: const TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w500,
                color: AppTheme.text,
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),
        PullRequestMetadata(
          repository: state.repository,
          baseBranch: state.baseBranch,
          headBranch: state.headBranch,
          filesChanged: state.filesChanged,
          validationPassed: state.validationPassed,
          reviewApproved: state.reviewApproved,
        ),
        if (state.prUrl != null && state.prUrl!.isNotEmpty) ...[
          const SizedBox(height: 16),
          SelectableText(
            state.prUrl!,
            style: const TextStyle(
              fontSize: 13,
              fontFamily: AppTheme.mono,
              color: AppTheme.accent,
            ),
          ),
        ],
        if (onViewPr != null && state.prUrl != null) ...[
          const SizedBox(height: 16),
          FilledButton.icon(
            onPressed: onViewPr,
            icon: const Icon(Icons.open_in_new, size: 15),
            label: const Text('View pull request'),
          ),
        ],
        if (onReturnToIssues != null) ...[
          const SizedBox(height: 32),
          const Divider(height: 1, color: AppTheme.borderSubtle),
          const SizedBox(height: 20),
          const Text(
            'Want to work on another issue?',
            style: TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w500,
              color: AppTheme.text,
            ),
          ),
          const SizedBox(height: 12),
          FilledButton(
            onPressed: onReturnToIssues,
            style: FilledButton.styleFrom(
              backgroundColor: AppTheme.accent,
              foregroundColor: Colors.white,
              elevation: 0,
              minimumSize: const Size(0, 44),
              padding: const EdgeInsets.symmetric(horizontal: 16),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(AppRadii.sm),
              ),
              textStyle: const TextStyle(
                fontSize: 13.5,
                fontWeight: FontWeight.w600,
              ),
            ),
            child: const Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text('Return to issues'),
                SizedBox(width: 8),
                Icon(Icons.arrow_forward, size: 16),
              ],
            ),
          ),
        ],
      ],
    );
  }
}

class PullRequestDemoCompleteView extends StatelessWidget {
  final PullRequestState state;
  final VoidCallback? onReturnToIssues;

  const PullRequestDemoCompleteView({
    super.key,
    required this.state,
    this.onReturnToIssues,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Row(
          children: [
            Icon(
              Icons.check_circle_outline,
              size: 20,
              color: AppTheme.success,
            ),
            SizedBox(width: 10),
            Text(
              'Repair complete',
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w500,
                color: AppTheme.text,
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        const Text(
          'Diagnosis, patch, validation, and review finished. This is a demo repository, so a GitHub pull request cannot be opened here.',
          style: TextStyle(
            fontSize: 13,
            height: 1.45,
            color: AppTheme.textMuted,
          ),
        ),
        const SizedBox(height: 20),
        PullRequestMetadata(
          repository: state.repository,
          baseBranch: state.baseBranch,
          headBranch: state.headBranch,
          filesChanged: state.filesChanged,
          validationPassed: state.validationPassed,
          reviewApproved: state.reviewApproved,
        ),
        if (onReturnToIssues != null) ...[
          const SizedBox(height: 32),
          const Divider(height: 1, color: AppTheme.borderSubtle),
          const SizedBox(height: 20),
          const Text(
            'Want to work on another issue?',
            style: TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w500,
              color: AppTheme.text,
            ),
          ),
          const SizedBox(height: 12),
          FilledButton(
            onPressed: onReturnToIssues,
            style: FilledButton.styleFrom(
              backgroundColor: AppTheme.accent,
              foregroundColor: Colors.white,
              elevation: 0,
              minimumSize: const Size(0, 44),
              padding: const EdgeInsets.symmetric(horizontal: 16),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(AppRadii.sm),
              ),
              textStyle: const TextStyle(
                fontSize: 13.5,
                fontWeight: FontWeight.w600,
              ),
            ),
            child: const Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text('Return to issues'),
                SizedBox(width: 8),
                Icon(Icons.arrow_forward, size: 16),
              ],
            ),
          ),
        ],
      ],
    );
  }
}

class PullRequestFailureView extends StatelessWidget {
  final String? errorMessage;
  final VoidCallback onRetry;

  const PullRequestFailureView({
    super.key,
    required this.errorMessage,
    required this.onRetry,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Row(
          children: [
            Icon(Icons.error_outline, size: 20, color: AppTheme.danger),
            SizedBox(width: 10),
            Text(
              'Pull request creation failed',
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w500,
                color: AppTheme.text,
              ),
            ),
          ],
        ),
        if (errorMessage != null && errorMessage!.trim().isNotEmpty) ...[
          const SizedBox(height: 12),
          SelectableText(
            errorMessage!,
            style: const TextStyle(
              fontSize: 13,
              fontFamily: AppTheme.mono,
              color: AppTheme.danger,
            ),
          ),
        ],
        const SizedBox(height: 16),
        FilledButton(onPressed: onRetry, child: const Text('Retry')),
      ],
    );
  }
}

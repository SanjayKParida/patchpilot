import 'package:flutter/material.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/core/widgets/common.dart';

import 'review_models.dart';
import 'review_widgets.dart';

class ReviewScreen extends StatelessWidget {
  final ReviewState state;
  final VoidCallback onApprove;
  final ValueChanged<String> onRequestChanges;
  final ValueChanged<ChangedFile>? onFileTap;

  const ReviewScreen({
    super.key,
    required this.state,
    required this.onApprove,
    required this.onRequestChanges,
    this.onFileTap,
  });

  @override
  Widget build(BuildContext context) {
    return PageBody(child: _buildContent(context));
  }

  Widget _buildContent(BuildContext context) {
    if (state.status == ReviewStatus.waiting) {
      return const _WaitingView();
    }

    if (state.status == ReviewStatus.approved) {
      return _ApprovedView(state: state, onFileTap: onFileTap);
    }

    if (state.status == ReviewStatus.changesRequested) {
      return _ChangesRequestedView(state: state);
    }

    return _ReadyForReviewView(
      state: state,
      onApprove: onApprove,
      onRequestChanges: () => _showRequestChangesDialog(context),
      onFileTap: onFileTap,
    );
  }

  void _showRequestChangesDialog(BuildContext context) {
    showDialog<void>(
      context: context,
      builder: (_) => RequestChangesDialog(onSubmit: onRequestChanges),
    );
  }
}

class _WaitingView extends StatelessWidget {
  const _WaitingView();

  @override
  Widget build(BuildContext context) {
    return const Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _PageHeader(
          title: 'Review',
          subtitle:
              'Review becomes available after the generated patch passes validation.',
        ),
        SizedBox(height: AppSpacing.section),
        Center(
          child: Column(
            children: [
              Icon(
                Icons.hourglass_empty_rounded,
                size: 28,
                color: AppTheme.textMuted,
              ),
              SizedBox(height: 14),
              Text(
                'Waiting for validation',
                style: TextStyle(
                  color: AppTheme.text,
                  fontSize: 14,
                  fontWeight: FontWeight.w500,
                ),
              ),
              SizedBox(height: 6),
              Text(
                'The patch can be reviewed once validation is complete.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: AppTheme.textMuted,
                  fontSize: 12,
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

class _ReadyForReviewView extends StatelessWidget {
  final ReviewState state;
  final VoidCallback onApprove;
  final VoidCallback onRequestChanges;
  final ValueChanged<ChangedFile>? onFileTap;

  const _ReadyForReviewView({
    required this.state,
    required this.onApprove,
    required this.onRequestChanges,
    this.onFileTap,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const _PageHeader(
          title: 'Review',
          status: ReviewStatusIndicator(status: ReviewStatus.ready),
        ),
        const SizedBox(height: AppSpacing.lg),
        ReviewDecisionBar(
          enabled: state.canApprove,
          onApprove: onApprove,
          onRequestChanges: onRequestChanges,
        ),
        if (state.validationPassed != true) ...[
          const SizedBox(height: AppSpacing.md),
          const _ApprovalBlockedMessage(),
        ],
        if (state.changedFiles.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.section),
          ChangedFilesSection(files: state.changedFiles, onFileTap: onFileTap),
        ],
        const SizedBox(height: AppSpacing.section),
        ReviewSummarySection(
          rootCause: state.rootCauseSummary,
          patchDescription: state.patchDescription,
        ),
        const SizedBox(height: AppSpacing.lg),
        ValidationResultSection(
          passed: state.validationPassed,
          warnings: state.validationWarnings,
        ),
        if (state.importantNotes.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.lg),
          ReviewNotesSection(notes: state.importantNotes),
        ],
      ],
    );
  }
}

class _ApprovedView extends StatelessWidget {
  final ReviewState state;
  final ValueChanged<ChangedFile>? onFileTap;

  const _ApprovedView({required this.state, this.onFileTap});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const _PageHeader(
          title: 'Review',
          subtitle: 'This patch has been approved.',
          status: ReviewStatusIndicator(status: ReviewStatus.approved),
        ),
        const SizedBox(height: AppSpacing.section),
        const _DecisionResult(
          icon: Icons.verified_outlined,
          title: 'Patch approved',
          description:
              'The patch is approved and ready for the Pull Request stage.',
        ),
        const SizedBox(height: AppSpacing.section),
        ReviewSummarySection(
          rootCause: state.rootCauseSummary,
          patchDescription: state.patchDescription,
        ),
        if (state.changedFiles.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.section),
          ChangedFilesSection(files: state.changedFiles, onFileTap: onFileTap),
        ],
      ],
    );
  }
}

class _ChangesRequestedView extends StatelessWidget {
  final ReviewState state;

  const _ChangesRequestedView({required this.state});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const _PageHeader(
          title: 'Review',
          subtitle: 'Changes have been requested for this patch.',
          status: ReviewStatusIndicator(status: ReviewStatus.changesRequested),
        ),
        const SizedBox(height: AppSpacing.section),
        _DecisionResult(
          icon: Icons.edit_outlined,
          title: 'Changes requested',
          description: state.feedback?.trim().isNotEmpty == true
              ? state.feedback!
              : 'Additional changes are required before this patch can be approved.',
        ),
        const SizedBox(height: AppSpacing.section),
        ReviewSummarySection(
          rootCause: state.rootCauseSummary,
          patchDescription: state.patchDescription,
        ),
      ],
    );
  }
}

class _PageHeader extends StatelessWidget {
  final String title;
  final String? subtitle;
  final Widget? status;

  const _PageHeader({required this.title, this.subtitle, this.status});

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: const TextStyle(
                  color: AppTheme.text,
                  fontSize: 18,
                  fontWeight: FontWeight.w600,
                  letterSpacing: -0.2,
                ),
              ),
              if (subtitle != null) ...[
                const SizedBox(height: 6),
                Text(
                  subtitle!,
                  style: const TextStyle(
                    color: AppTheme.textMuted,
                    fontSize: 12.5,
                    height: 1.4,
                  ),
                ),
              ],
            ],
          ),
        ),
        if (status != null) ...[
          const SizedBox(width: 24),
          Padding(padding: const EdgeInsets.only(top: 4), child: status!),
        ],
      ],
    );
  }
}

class _DecisionResult extends StatelessWidget {
  final IconData icon;
  final String title;
  final String description;

  const _DecisionResult({
    required this.icon,
    required this.title,
    required this.description,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 16),
      decoration: const BoxDecoration(
        border: Border(
          top: BorderSide(color: AppTheme.border),
          bottom: BorderSide(color: AppTheme.border),
        ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 20, color: AppTheme.textMuted),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    color: AppTheme.text,
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 5),
                Text(
                  description,
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

class _ApprovalBlockedMessage extends StatelessWidget {
  const _ApprovalBlockedMessage();

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.only(bottom: 14),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.info_outline, size: 16, color: AppTheme.warning),
          SizedBox(width: 8),
          Expanded(
            child: Text(
              'Approval is unavailable until validation passes successfully.',
              style: TextStyle(
                color: AppTheme.textMuted,
                fontSize: 12,
                height: 1.4,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

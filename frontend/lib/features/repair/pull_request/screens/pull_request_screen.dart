import 'package:flutter/material.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/core/widgets/common.dart';
import 'package:patchpilot_web/core/widgets/motion.dart';
import 'package:patchpilot_web/features/repair/shell/repair_section_help.dart';

import 'pull_request_models.dart';
import 'pull_request_widgets.dart';

class PullRequestScreen extends StatefulWidget {
  final PullRequestState state;

  /// Anonymous demo users must connect GitHub before Create PR.
  final bool needsGithubConnect;

  /// Demo repositories cannot open a GitHub pull request.
  final bool isDemo;

  final Future<void> Function()? onConnectGithub;

  /// Called with the current title and description.
  final void Function(String title, String description) onCreatePr;

  final VoidCallback onRetry;

  /// Called only when a real PR URL exists.
  final VoidCallback? onViewPr;

  /// Returns to the repository Issues screen after a successful PR.
  final VoidCallback? onReturnToIssues;

  const PullRequestScreen({
    super.key,
    required this.state,
    required this.onCreatePr,
    required this.onRetry,
    this.needsGithubConnect = false,
    this.isDemo = false,
    this.onConnectGithub,
    this.onViewPr,
    this.onReturnToIssues,
  });

  @override
  State<PullRequestScreen> createState() => _PullRequestScreenState();
}

class _PullRequestScreenState extends State<PullRequestScreen> {
  late final TextEditingController _titleController;
  late final TextEditingController _descriptionController;

  @override
  void initState() {
    super.initState();

    _titleController = TextEditingController(text: widget.state.title);

    _descriptionController = TextEditingController(
      text: widget.state.description,
    );
  }

  @override
  void didUpdateWidget(PullRequestScreen oldWidget) {
    super.didUpdateWidget(oldWidget);

    if (widget.state.title != oldWidget.state.title &&
        widget.state.title != _titleController.text) {
      _titleController.text = widget.state.title;
    }

    if (widget.state.description != oldWidget.state.description &&
        widget.state.description != _descriptionController.text) {
      _descriptionController.text = widget.state.description;
    }
  }

  @override
  void dispose() {
    _titleController.dispose();
    _descriptionController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = widget.state;

    return PageBody(child: _buildContent(state));
  }

  Widget _buildContent(PullRequestState state) {
    if (state.isCreated) {
      return PullRequestCreatedView(
        state: state,
        onViewPr: state.prUrl != null ? widget.onViewPr : null,
        onReturnToIssues: widget.onReturnToIssues,
      );
    }

    if (widget.isDemo && !widget.needsGithubConnect) {
      return PullRequestDemoCompleteView(
        state: state,
        onReturnToIssues: widget.onReturnToIssues,
      );
    }

    if (state.isFailed) {
      return PullRequestFailureView(
        errorMessage: state.errorMessage,
        onRetry: widget.onRetry,
      );
    }

    return _buildReadyState(state);
  }

  Widget _buildReadyState(PullRequestState state) {
    final canEdit = state.status == PullRequestStatus.ready;
    final canCreate = state.canCreate;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Text(
              'Pull request',
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.w500,
                color: AppTheme.text,
              ),
            ),
            const SectionInfoButton(message: RepairSectionHelp.pullRequest),
            const Spacer(),
            PullRequestStatusIndicator(status: state.status),
          ],
        ),

        const SizedBox(height: 20),

        if (widget.needsGithubConnect)
          _GithubConnectPrerequisite(onConnectGithub: widget.onConnectGithub)
        else if (state.isCreating)
          const Row(
            children: [
              AppSpinner(size: 16),
              SizedBox(width: 10),
              Text(
                'Creating pull request…',
                style: TextStyle(color: AppTheme.text, fontSize: 13),
              ),
            ],
          )
        else
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              onPressed: canCreate
                  ? () => widget.onCreatePr(
                      _titleController.text.trim(),
                      _descriptionController.text.trim(),
                    )
                  : null,
              style: FilledButton.styleFrom(
                minimumSize: const Size(0, 46),
                padding: const EdgeInsets.symmetric(horizontal: 18),
              ),
              child: const Text('Create pull request'),
            ),
          ),

        if (!widget.needsGithubConnect &&
            !canCreate &&
            state.status == PullRequestStatus.ready) ...[
          const SizedBox(height: 10),
          const Text(
            'A successful validation and approved review are required.',
            style: TextStyle(color: AppTheme.textMuted, fontSize: 12),
          ),
        ],

        const SizedBox(height: 28),

        const PullRequestSectionLabel(
          'Change summary',
          info: RepairSectionHelp.changeSummary,
        ),
        const SizedBox(height: 12),

        PullRequestMetadata(
          repository: state.repository,
          baseBranch: state.baseBranch,
          headBranch: state.headBranch,
          filesChanged: state.filesChanged,
          validationPassed: state.validationPassed,
          reviewApproved: state.reviewApproved,
        ),

        const SizedBox(height: 28),

        PullRequestField(
          label: 'Title',
          hint: 'Summary of the change',
          controller: _titleController,
          enabled: canEdit,
        ),

        const SizedBox(height: 18),

        PullRequestField(
          label: 'Description',
          hint: 'Describe the problem, root cause, change, and validation',
          controller: _descriptionController,
          enabled: canEdit,
          maxLines: 7,
        ),

        const SizedBox(height: 28),

        PullRequestPrerequisites(
          validationPassed: state.validationPassed,
          reviewApproved: state.reviewApproved,
        ),
      ],
    );
  }
}

class _GithubConnectPrerequisite extends StatefulWidget {
  final Future<void> Function()? onConnectGithub;

  const _GithubConnectPrerequisite({this.onConnectGithub});

  @override
  State<_GithubConnectPrerequisite> createState() =>
      _GithubConnectPrerequisiteState();
}

class _GithubConnectPrerequisiteState extends State<_GithubConnectPrerequisite> {
  bool _connecting = false;

  Future<void> _connect() async {
    final onConnectGithub = widget.onConnectGithub;
    if (onConnectGithub == null || _connecting) return;

    setState(() => _connecting = true);
    try {
      await onConnectGithub();
    } finally {
      if (mounted) setState(() => _connecting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'Connect GitHub to create this pull request',
          style: TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w500,
            color: AppTheme.text,
          ),
        ),
        const SizedBox(height: 12),
        const Text(
          'PatchPilot can analyze and validate this demo issue without GitHub access. Creating a pull request requires a GitHub account with write access to the repository.',
          style: TextStyle(fontSize: 13, color: AppTheme.textMuted),
        ),
        const SizedBox(height: 16),
        SizedBox(
          width: double.infinity,
          child: FilledButton(
            onPressed: widget.onConnectGithub == null || _connecting
                ? null
                : _connect,
            style: FilledButton.styleFrom(
              minimumSize: const Size(0, 46),
              padding: const EdgeInsets.symmetric(horizontal: 18),
            ),
            child: _connecting
                ? const AppSpinner(size: 16, color: Colors.white)
                : const Text('Connect GitHub →'),
          ),
        ),
      ],
    );
  }
}

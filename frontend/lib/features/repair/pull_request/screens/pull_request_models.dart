import 'package:patchpilot_web/models/models.dart';

enum PullRequestStatus { ready, creating, created, failed }

class PullRequestState {
  final PullRequestStatus status;

  final String repository;
  final String baseBranch;
  final String headBranch;

  final String title;
  final String description;

  final int filesChanged;

  final int? prNumber;
  final String? prUrl;
  final String? errorMessage;

  /// Null means validation has not been established.
  final bool? validationPassed;

  /// Null means review has not been established.
  final bool? reviewApproved;

  const PullRequestState({
    this.status = PullRequestStatus.ready,
    this.repository = '',
    this.baseBranch = '',
    this.headBranch = '',
    this.title = '',
    this.description = '',
    this.filesChanged = 0,
    this.prNumber,
    this.prUrl,
    this.errorMessage,
    this.validationPassed,
    this.reviewApproved,
  });

  bool get canCreate =>
      status == PullRequestStatus.ready &&
      validationPassed == true &&
      reviewApproved == true;

  bool get isCreating => status == PullRequestStatus.creating;

  bool get isCreated => status == PullRequestStatus.created;

  bool get isFailed => status == PullRequestStatus.failed;

  /// Maps stored patch, validation, approval, and delivery artifacts.
  /// Missing validation is never treated as passed.
  factory PullRequestState.fromArtifacts({
    required String repository,
    required String baseBranch,
    Diagnosis? diagnosis,
    PatchProposal? proposal,
    PatchValidationResult? validation,
    PatchApproval? approval,
    PatchDelivery? delivery,
    bool delivering = false,
    String? errorMessage,
  }) {
    final validationPassed = validation?.isPassed;
    final reviewApproved = approval?.approved;

    final PullRequestStatus status;
    if (delivering || delivery?.isRunning == true) {
      status = PullRequestStatus.creating;
    } else if (delivery?.isSucceeded == true) {
      status = PullRequestStatus.created;
    } else if (delivery?.isFailed == true ||
        (errorMessage != null && errorMessage.trim().isNotEmpty)) {
      status = PullRequestStatus.failed;
    } else {
      status = PullRequestStatus.ready;
    }

    final description = [
      if ((diagnosis?.rootCause ?? '').trim().isNotEmpty)
        diagnosis!.rootCause.trim(),
      if ((proposal?.summary ?? '').trim().isNotEmpty) proposal!.summary.trim(),
      if ((proposal?.reasoning ?? '').trim().isNotEmpty)
        proposal!.reasoning.trim(),
    ].join('\n\n');

    final deliveryError = delivery == null || delivery.errors.isEmpty
        ? null
        : delivery.errors.join('\n');

    return PullRequestState(
      status: status,
      repository: repository,
      baseBranch: baseBranch,
      headBranch: delivery?.branch ?? '',
      title: (proposal?.summary ?? '').trim(),
      description: description,
      filesChanged: proposal?.files.length ?? 0,
      prNumber: delivery?.prNumber,
      prUrl: delivery?.prUrl,
      errorMessage: errorMessage ?? deliveryError,
      validationPassed: validationPassed,
      reviewApproved: reviewApproved,
    );
  }
}

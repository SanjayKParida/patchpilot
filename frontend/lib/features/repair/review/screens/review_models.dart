import 'package:patchpilot_web/models/models.dart';

enum ReviewStatus { waiting, ready, changesRequested, approved }

class ChangedFile {
  final String path;
  final int additions;
  final int deletions;
  final int? highlightLine;

  const ChangedFile({
    required this.path,
    this.additions = 0,
    this.deletions = 0,
    this.highlightLine,
  });

  int get totalChanges => additions + deletions;

  factory ChangedFile.fromPatchFile(PatchFile file) {
    var additions = 0;
    var deletions = 0;
    for (final hunk in file.hunks) {
      additions += _lineCount(hunk.newText);
      deletions += _lineCount(hunk.oldText);
    }
    return ChangedFile(
      path: file.path,
      additions: additions,
      deletions: deletions,
      highlightLine: file.hunks.isEmpty ? null : file.hunks.first.startLine,
    );
  }
}

int _lineCount(String text) {
  if (text.isEmpty) return 0;
  return text.split('\n').length;
}

class ReviewState {
  final ReviewStatus status;
  final String rootCauseSummary;
  final String patchDescription;
  final List<ChangedFile> changedFiles;
  final bool? validationPassed;
  final List<String> validationWarnings;
  final List<String> importantNotes;
  final String? feedback;

  const ReviewState({
    this.status = ReviewStatus.waiting,
    this.rootCauseSummary = '',
    this.patchDescription = '',
    this.changedFiles = const [],
    this.validationPassed,
    this.validationWarnings = const [],
    this.importantNotes = const [],
    this.feedback,
  });

  bool get isWaiting => status == ReviewStatus.waiting;

  bool get isReady => status == ReviewStatus.ready;

  bool get isApproved => status == ReviewStatus.approved;

  bool get hasValidationWarnings => validationWarnings.isNotEmpty;

  bool get canApprove =>
      status == ReviewStatus.ready && validationPassed == true;

  /// Builds review presentation from stored diagnosis, patch, and
  /// validation artifacts. Missing validation is never treated as passed.
  factory ReviewState.fromArtifacts({
    Diagnosis? diagnosis,
    PatchProposal? proposal,
    PatchValidationResult? validation,
    bool approved = false,
    String? feedback,
  }) {
    final validationPassed = validation?.isPassed;

    final ReviewStatus status;
    if (approved) {
      status = ReviewStatus.approved;
    } else if (validationPassed == true) {
      status = ReviewStatus.ready;
    } else {
      status = ReviewStatus.waiting;
    }

    final description = [
      if ((proposal?.summary ?? '').trim().isNotEmpty) proposal!.summary.trim(),
      if ((proposal?.reasoning ?? '').trim().isNotEmpty)
        proposal!.reasoning.trim(),
    ].join('\n\n');

    final notes = <String>[
      ...?proposal?.warnings,
      ...?proposal?.errors,
      if (feedback != null && feedback.trim().isNotEmpty)
        'Requested changes: ${feedback.trim()}',
      if (validation != null && validation.isUnavailable)
        validation.unavailableReason.isEmpty
            ? 'Validation could not run Flutter checks against the '
                  'pinned repository snapshot.'
            : validation.unavailableReason,
    ];

    return ReviewState(
      status: status,
      rootCauseSummary: diagnosis?.rootCause ?? '',
      patchDescription: description,
      changedFiles: [
        for (final file in proposal?.files ?? const <PatchFile>[])
          ChangedFile.fromPatchFile(file),
      ],
      validationPassed: validationPassed,
      validationWarnings: validation?.warnings ?? const [],
      importantNotes: notes,
      feedback: feedback,
    );
  }
}

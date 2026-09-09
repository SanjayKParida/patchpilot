/// Product copy for repair-stage section info buttons.
///
/// Call sites pass these strings into [SectionTitle.info] or
/// [SectionInfoButton.message]. This class does not render UI.
abstract final class RepairSectionHelp {
  static const rootCause = "The model's primary defect claim for this issue.";

  static const explanation =
      'Why that claim is believed, based on retrieved evidence.';

  static const relevantFiles =
      'Retrieval-ranked files that grounded this diagnosis.';

  static const signals = 'Issue terms matched into the codebase.';

  static const suggestedFix =
      'Proposed remediation direction. This is not yet a patch.';

  static const followUp =
      'Ask one question about this analysis. Each answer uses this '
      'analysis only, with no memory of earlier questions.';

  static const context =
      'Bounded code slices retrieved to give the patch generator '
      'relevant repository context.';

  static const selectedContext =
      'The specific slices currently included in the patch-generation '
      'context.';

  static const proposedPatch =
      'Structured change proposal generated from the diagnosis and context.';

  static const validationSteps =
      'Checks that will run if validation is available for this proposal.';

  static const validation =
      'Sandbox and command validation of the proposed patch.';

  static const validationChecks = 'The list of checks run for this proposal.';

  static const review = 'Human review gate before a pull request is created.';

  static const whatChanged = 'Summary of the diagnosis and patch under review.';

  static const changedFiles = 'Files touched by the proposed patch.';

  static const reviewValidation =
      'Validation evidence considered during the review decision.';

  static const notes = 'Notes and limitations to weigh before approving.';

  static const pullRequest =
      'Draft pull request creation for the approved change.';

  static const changeSummary =
      'Title and body content that will be used for the pull request.';

  static const prerequisites =
      'Conditions that must be true before creating the pull request.';
}

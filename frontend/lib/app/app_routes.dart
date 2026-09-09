import 'package:patchpilot_web/features/repair/shell/repair_workflow.dart';
import 'package:patchpilot_web/models/models.dart';

/// Path helpers for the app-level GoRouter.
///
/// GoRouter owns history; these strings are the only URL contract.
abstract final class AppRoutes {
  static const dashboard = '/';

  static String issues(String owner, String repo) => '/r/$owner/$repo';

  static String repair({
    required String owner,
    required String repo,
    required int number,
    RepairStage stage = RepairStage.diagnosis,
    String? ref,
  }) {
    final path = '/r/$owner/$repo/issues/$number/${segmentFor(stage)}';
    final trimmed = ref?.trim();
    if (trimmed == null || trimmed.isEmpty) return path;
    return Uri(path: path, queryParameters: {'ref': trimmed}).toString();
  }

  static String segmentFor(RepairStage stage) {
    switch (stage) {
      case RepairStage.patch:
      case RepairStage.context:
        return 'patch';
      case RepairStage.validation:
        return 'validation';
      case RepairStage.review:
        return 'review';
      case RepairStage.pullRequest:
        return 'pull-request';
      case RepairStage.diagnosis:
      case RepairStage.issue:
        return 'diagnosis';
    }
  }

  static RepairStage stageFrom(String? segment) {
    switch ((segment ?? '').trim().toLowerCase()) {
      case 'patch':
      case 'context':
        return RepairStage.patch;
      case 'validation':
        return RepairStage.validation;
      case 'review':
        return RepairStage.review;
      case 'pull-request':
        return RepairStage.pullRequest;
      default:
        return RepairStage.diagnosis;
    }
  }

  static Repository repositoryFromPath(String owner, String repo) {
    return Repository(owner: owner, repo: repo, fullName: '$owner/$repo');
  }
}

/// Live models carried through [GoRouter.extra] so in-app navigation
/// keeps issue title/body and repository metadata. Missing on refresh.
class RepairNavExtra {
  final Repository repository;
  final Issue issue;

  const RepairNavExtra({required this.repository, required this.issue});
}

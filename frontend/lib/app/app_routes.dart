import 'package:patchpilot_web/features/repair/shell/repair_workflow.dart';
import 'package:patchpilot_web/models/models.dart';

/// Path helpers for the app-level GoRouter.
///
/// GoRouter owns history; these strings are the only URL contract.
abstract final class AppRoutes {
  static const dashboard = '/';
  static const appTitle = 'PatchPilot';

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
    return knownStageFrom(segment) ?? RepairStage.diagnosis;
  }

  /// Known repair URL segments only. Unknown values are null so callers
  /// such as the document title can fall back instead of assuming
  /// diagnosis.
  static RepairStage? knownStageFrom(String? segment) {
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
      case 'diagnosis':
        return RepairStage.diagnosis;
      default:
        return null;
    }
  }

  /// Browser tab title for the current GoRouter location.
  static String documentTitle(Uri? location) {
    final path = location?.path ?? '';
    final normalized = path.isEmpty ? dashboard : path;
    if (normalized == dashboard) return appTitle;

    final parts = normalized.split('/').where((part) => part.isNotEmpty).toList();
    if (parts.length == 3 && parts[0] == 'r') {
      return 'Issues · $appTitle';
    }
    if (parts.length >= 6 && parts[0] == 'r' && parts[3] == 'issues') {
      final stage = knownStageFrom(parts[5]);
      if (stage != null) return '${stage.label} · $appTitle';
    }
    return appTitle;
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

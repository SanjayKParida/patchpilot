// validation_models.dart
import 'package:patchpilot_web/models/models.dart';

enum ValidationStatus { notStarted, running, passed, failed, unavailable }

enum CheckStatus { pending, running, passed, failed }

class ValidationCheck {
  final String id;
  final String label;
  final String? detail;
  final CheckStatus status;
  final String? log;
  final String? error;

  const ValidationCheck({
    required this.id,
    required this.label,
    this.detail,
    this.status = CheckStatus.pending,
    this.log,
    this.error,
  });

  bool get hasOutput =>
      (log != null && log!.isNotEmpty) || (error != null && error!.isNotEmpty);
}

class ValidationState {
  final ValidationStatus overallStatus;
  final List<ValidationCheck> checks;
  final String? globalLog;
  final String? summary;
  final String? errorMessage;
  final List<String> warnings;
  final bool canRun;

  const ValidationState({
    this.overallStatus = ValidationStatus.notStarted,
    this.checks = const [],
    this.globalLog,
    this.summary,
    this.errorMessage,
    this.warnings = const [],
    this.canRun = false,
  });

  int get completedChecks => checks
      .where(
        (check) =>
            check.status == CheckStatus.passed ||
            check.status == CheckStatus.failed,
      )
      .length;

  int get passedChecks =>
      checks.where((check) => check.status == CheckStatus.passed).length;

  int get failedChecks =>
      checks.where((check) => check.status == CheckStatus.failed).length;

  bool get hasChecks => checks.isNotEmpty;

  bool get hasFailures => failedChecks > 0;

  bool get hasLogs =>
      (globalLog != null && globalLog!.isNotEmpty) ||
      checks.any((check) => check.hasOutput);

  /// Maps a stored or freshly POSTed [PatchValidationResult] into the
  /// view model the Validation stage renders.
  ///
  /// [knownChecks] is optional context from the *last real result* for
  /// this analysis (if one exists). It is only consulted while
  /// [running] is true and no fresh result has arrived yet: the pipeline
  /// shape it describes is genuine (it came from a real prior
  /// completion), but every check is reset to [CheckStatus.pending]
  /// because we have no way to know real-time progress mid-run. This
  /// never fabricates a pass/fail/running state that wasn't reported.
  factory ValidationState.fromResult({
    required bool running,
    required bool canRun,
    PatchValidationResult? result,
    String? errorMessage,
    List<ValidationCheck>? knownChecks,
  }) {
    if (running) {
      final pipelinePreview = (knownChecks ?? const <ValidationCheck>[])
          .map((check) => ValidationCheck(id: check.id, label: check.label))
          .toList();
      return ValidationState(
        overallStatus: ValidationStatus.running,
        checks: pipelinePreview,
        canRun: canRun,
        errorMessage: errorMessage,
      );
    }

    if (result == null) {
      return ValidationState(
        overallStatus: ValidationStatus.notStarted,
        canRun: canRun,
        errorMessage: errorMessage,
      );
    }

    return ValidationState(
      overallStatus: _overallStatus(result),
      checks: _checksFrom(result),
      summary: _summary(result),
      errorMessage:
          errorMessage ??
          (result.errors.isEmpty ? null : result.errors.join('\n')),
      warnings: result.warnings,
      canRun: canRun,
    );
  }
}

ValidationStatus _overallStatus(PatchValidationResult result) {
  if (result.isPassed) return ValidationStatus.passed;
  if (result.isUnavailable) return ValidationStatus.unavailable;
  if (result.isFailed) return ValidationStatus.failed;
  return ValidationStatus.failed;
}

String? _summary(PatchValidationResult result) {
  if (result.isPassed) {
    return 'The generated patch applied and passed Flutter checks.';
  }
  if (result.isUnavailable) {
    if (result.unavailableReason.isNotEmpty) return result.unavailableReason;
    return 'Validation could not run Flutter checks against the '
        'pinned repository snapshot.';
  }
  if (result.errors.isNotEmpty) return result.errors.first;
  return null;
}

List<ValidationCheck> _checksFrom(PatchValidationResult result) {
  return [
    ValidationCheck(
      id: 'apply',
      label: 'Patch applied',
      detail: result.applied ? 'applied' : 'apply failed',
      status: result.applied ? CheckStatus.passed : CheckStatus.failed,
      error: result.applied
          ? null
          : (result.errors.isNotEmpty ? result.errors.first : 'apply failed'),
    ),
    for (final command in result.commands) _checkFromCommand(command),
  ];
}

ValidationCheck _checkFromCommand(ValidationCommandResult command) {
  final stdout = command.stdout.trim();
  final stderr = command.stderr.trim();
  String? error;
  if (command.timedOut) {
    error = 'timed out';
  } else if (!command.passed) {
    error = stderr.isNotEmpty ? stderr : 'exit ${command.exitCode ?? '?'}';
  }

  return ValidationCheck(
    id: command.name.isNotEmpty ? command.name : command.displayName,
    label: command.displayName,
    detail: _commandDetail(command),
    status: command.passed ? CheckStatus.passed : CheckStatus.failed,
    log: stdout.isEmpty ? null : stdout,
    error: error,
  );
}

String _commandDetail(ValidationCommandResult command) {
  if (command.timedOut) return 'timed out';
  if (command.passed && (command.exitCode ?? 0) != 0) {
    return 'exit ${command.exitCode} · no new diagnostics';
  }
  final exit = 'exit ${command.exitCode ?? '?'}';
  if (command.durationMs > 0) return '$exit · ${command.durationMs}ms';
  return exit;
}

// Response models mirroring the PatchPilot API contract.
//
// Every model parses defensively: the API is a separate process and a
// missing or renamed field must degrade the UI, never crash it.

class Repository {
  final String owner;
  final String repo;
  final String fullName;
  final String? description;
  final bool private;
  final bool demo;
  final bool? canRead;
  final bool? canWrite;
  final String? access;

  const Repository({
    required this.owner,
    required this.repo,
    required this.fullName,
    this.description,
    this.private = false,
    this.demo = false,
    this.canRead,
    this.canWrite,
    this.access,
  });

  factory Repository.fromJson(Map<String, dynamic> json) {
    return Repository(
      owner: json['owner'] as String? ?? '',
      repo: json['repo'] as String? ?? '',
      fullName: json['full_name'] as String? ?? '',
      description: json['description'] as String?,
      private: json['private'] as bool? ?? false,
      demo: json['demo'] as bool? ?? false,
      canRead: json['can_read'] as bool?,
      canWrite: json['can_write'] as bool?,
      access: json['access'] as String?,
    );
  }

  Map<String, dynamic> toJson() => {
        'owner': owner,
        'repo': repo,
        'full_name': fullName,
        'description': description,
        'private': private,
        'demo': demo,
        'can_read': canRead,
        'can_write': canWrite,
        'access': access,
      };
}

class RepositorySnapshot {
  final String commitSha;
  final String status;
  final int fileCount;
  final int progressPercent;
  final int filesDownloaded;
  final int filesTotal;

  const RepositorySnapshot({
    required this.commitSha,
    required this.status,
    this.fileCount = 0,
    this.progressPercent = 0,
    this.filesDownloaded = 0,
    this.filesTotal = 0,
  });

  bool get isReady => status == 'ready';
  bool get isRunning => status == 'running';
  bool get isMissing => status == 'missing';

  factory RepositorySnapshot.fromJson(Map<String, dynamic> json) {
    return RepositorySnapshot(
      commitSha: json['commit_sha'] as String? ?? '',
      status: json['status'] as String? ?? 'missing',
      fileCount: json['file_count'] as int? ?? 0,
      progressPercent: json['progress_percent'] as int? ?? 0,
      filesDownloaded: json['files_downloaded'] as int? ?? 0,
      filesTotal: json['files_total'] as int? ?? 0,
    );
  }
}

class AuthUser {
  final String id;
  final int githubId;
  final String githubLogin;
  final String avatarUrl;
  final String name;

  const AuthUser({
    required this.id,
    required this.githubId,
    required this.githubLogin,
    this.avatarUrl = '',
    this.name = '',
  });

  String get displayName => name.isNotEmpty ? name : githubLogin;

  factory AuthUser.fromJson(Map<String, dynamic> json) {
    return AuthUser(
      id: json['id'] as String? ?? '',
      githubId: json['github_id'] as int? ?? 0,
      githubLogin: json['github_login'] as String? ?? '',
      avatarUrl: json['avatar_url'] as String? ?? '',
      name: json['name'] as String? ?? '',
    );
  }
}

class AuthMe {
  final bool authenticated;
  final AuthUser? user;

  const AuthMe({required this.authenticated, this.user});

  factory AuthMe.fromJson(Map<String, dynamic> json) {
    final userJson = json['user'];
    return AuthMe(
      authenticated: json['authenticated'] as bool? ?? false,
      user: userJson is Map<String, dynamic>
          ? AuthUser.fromJson(userJson)
          : null,
    );
  }
}

class Issue {
  final int number;
  final String title;
  final String body;
  final String state;
  final int comments;

  const Issue({
    required this.number,
    required this.title,
    this.body = '',
    this.state = 'open',
    this.comments = 0,
  });

  bool get isOpen => state.toLowerCase() == 'open';

  /// A short, single-line preview for the issue list.
  String get snippet {
    final collapsed = body.replaceAll(RegExp(r'\s+'), ' ').trim();
    if (collapsed.length <= 160) return collapsed;
    return '${collapsed.substring(0, 160)}…';
  }

  factory Issue.fromJson(Map<String, dynamic> json) {
    return Issue(
      number: json['number'] as int? ?? 0,
      title: json['title'] as String? ?? '',
      body: json['body'] as String? ?? '',
      state: json['state'] as String? ?? 'open',
      comments: json['comments'] as int? ?? 0,
    );
  }
}

class Signal {
  final String term;
  final String type;

  const Signal({required this.term, required this.type});

  factory Signal.fromJson(Map<String, dynamic> json) => Signal(
        term: json['term'] as String? ?? '',
        type: json['type'] as String? ?? 'domain',
      );
}

class EvidenceItem {
  final String concept;
  final String kind;
  final String identifier;
  final int line;

  const EvidenceItem({
    required this.concept,
    required this.kind,
    required this.identifier,
    required this.line,
  });

  factory EvidenceItem.fromJson(Map<String, dynamic> json) => EvidenceItem(
        concept: json['concept'] as String? ?? '',
        kind: json['kind'] as String? ?? '',
        identifier: json['identifier'] as String? ?? '',
        line: json['line'] as int? ?? 0,
      );
}

class StructuralEdge {
  final String relationship;
  final String source;
  final int distance;

  const StructuralEdge({
    required this.relationship,
    required this.source,
    required this.distance,
  });

  String get sourceName => source.split('/').last;

  /// Reads as a sentence in the UI: "imports from car_bloc.dart".
  String get label => '$relationship from $sourceName';

  factory StructuralEdge.fromJson(Map<String, dynamic> json) =>
      StructuralEdge(
        relationship: json['relationship'] as String? ?? '',
        source: json['source'] as String? ?? '',
        distance: json['distance'] as int? ?? 0,
      );
}

class RelevantFile {
  final int rank;
  final String path;
  final double totalScore;
  final int signalsMatched;
  final List<EvidenceItem> evidence;
  final List<StructuralEdge> structural;

  const RelevantFile({
    required this.rank,
    required this.path,
    required this.totalScore,
    required this.signalsMatched,
    required this.evidence,
    required this.structural,
  });

  String get fileName => path.split('/').last;

  String get directory {
    final parts = path.split('/');
    if (parts.length < 2) return '';
    return parts.sublist(0, parts.length - 1).join('/');
  }

  factory RelevantFile.fromJson(Map<String, dynamic> json) => RelevantFile(
        rank: json['rank'] as int? ?? 0,
        path: json['path'] as String? ?? '',
        totalScore: (json['total_score'] as num?)?.toDouble() ?? 0,
        signalsMatched: json['signals_matched'] as int? ?? 0,
        evidence: (json['evidence'] as List<dynamic>? ?? [])
            .map((e) => EvidenceItem.fromJson(e as Map<String, dynamic>))
            .toList(),
        structural: (json['structural'] as List<dynamic>? ?? [])
            .map((e) => StructuralEdge.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

/// Where a symbol the diagnosis named is declared.
///
/// Resolved from the source by the backend, never reported by the
/// model — see DartSymbolLocator.
class SymbolLocation {
  final String symbol;
  final String path;
  final int line;
  final String kind;

  const SymbolLocation({
    required this.symbol,
    required this.path,
    required this.line,
    required this.kind,
  });

  String get fileName => path.split('/').last;

  String get label => '$fileName:$line';

  factory SymbolLocation.fromJson(Map<String, dynamic> json) =>
      SymbolLocation(
        symbol: json['symbol'] as String? ?? '',
        path: json['path'] as String? ?? '',
        line: json['line'] as int? ?? 0,
        kind: json['kind'] as String? ?? '',
      );
}

class Diagnosis {
  final String rootCause;

  /// Probability in [0, 1] as reported by the diagnosis service.
  final double confidence;
  final String explanation;
  final String suggestedFix;

  /// Files the diagnosis actually leans on, a subset of the ranked set.
  final List<String> citedFiles;

  /// Supporting declarations that explain the failure. These are NOT
  /// the defect site and must never drive "View root cause".
  final List<SymbolLocation> locations;

  /// The declaration containing the defect, resolved to file and line.
  final List<SymbolLocation> rootCauseLocations;

  const Diagnosis({
    required this.rootCause,
    required this.confidence,
    required this.explanation,
    required this.suggestedFix,
    required this.citedFiles,
    this.locations = const [],
    this.rootCauseLocations = const [],
  });

  /// Where "View root cause" goes.
  ///
  /// Only ever a resolved ROOT CAUSE symbol. When none resolved this
  /// is null and the caller falls back to the affected file — sending
  /// someone to an arbitrary supporting type would be worse than
  /// sending them to the right file with no line.
  SymbolLocation? get rootCauseLocation =>
      rootCauseLocations.isEmpty ? null : rootCauseLocations.first;

  /// The file to open when no root-cause symbol resolved.
  String? get affectedFile =>
      citedFiles.isEmpty ? null : citedFiles.first;

  String get confidencePercent =>
      '${(confidence * 100).round()}% confidence';

  String get confidenceBand {
    if (confidence >= 0.7) return 'high';
    if (confidence >= 0.4) return 'medium';
    return 'low';
  }

  factory Diagnosis.fromJson(Map<String, dynamic> json) => Diagnosis(
        rootCause: json['root_cause'] as String? ?? '',
        confidence: (json['confidence'] as num?)?.toDouble() ?? 0,
        explanation: json['explanation'] as String? ?? '',
        suggestedFix: json['suggested_fix'] as String? ?? '',
        citedFiles: (json['relevant_files'] as List<dynamic>? ?? [])
            .map((e) => e.toString())
            .toList(),
        locations: (json['locations'] as List<dynamic>? ?? [])
            .map((e) => SymbolLocation.fromJson(e as Map<String, dynamic>))
            .toList(),
        rootCauseLocations:
            (json['root_cause_locations'] as List<dynamic>? ?? [])
                .map((e) =>
                    SymbolLocation.fromJson(e as Map<String, dynamic>))
                .toList(),
      );
}

enum AnalysisStatus { queued, running, completed, failed }

class Analysis {
  final String id;
  final AnalysisStatus status;
  final String? stage;
  final String? error;
  final int issueNumber;
  final Issue? issue;
  final List<Signal> signals;
  final List<RelevantFile> relevantFiles;
  final Diagnosis? diagnosis;
  final String? diagnosisError;
  final String? ref;
  final String? commitSha;

  const Analysis({
    required this.id,
    required this.status,
    required this.issueNumber,
    this.stage,
    this.error,
    this.issue,
    this.signals = const [],
    this.relevantFiles = const [],
    this.diagnosis,
    this.diagnosisError,
    this.ref,
    this.commitSha,
  });

  bool get isTerminal =>
      status == AnalysisStatus.completed || status == AnalysisStatus.failed;

  /// Human-readable description of the current pipeline stage.
  String get stageLabel {
    switch (stage) {
      case 'fetching_issue':
        return 'Reading the issue';
      case 'fetching_source':
        return 'Downloading repository source';
      case 'extracting_signals':
        return 'Extracting signals';
      case 'ranking':
        return 'Ranking candidate files';
      case 'diagnosing':
        return 'Diagnosing root cause';
      case 'building_context':
        return 'Building repository context';
      default:
        return 'Starting analysis';
    }
  }

  factory Analysis.fromJson(Map<String, dynamic> json) {
    final rawIssue = json['issue'] as Map<String, dynamic>?;
    final rawDiagnosis = json['diagnosis'] as Map<String, dynamic>?;

    return Analysis(
      id: json['id'] as String? ?? '',
      status: _statusFrom(json['status'] as String?),
      stage: json['stage'] as String?,
      error: json['error'] as String?,
      issueNumber: json['issue_number'] as int? ?? 0,
      issue: rawIssue == null ? null : Issue.fromJson(rawIssue),
      signals: (json['signals'] as List<dynamic>? ?? [])
          .map((e) => Signal.fromJson(e as Map<String, dynamic>))
          .toList(),
      relevantFiles: (json['relevant_files'] as List<dynamic>? ?? [])
          .map((e) => RelevantFile.fromJson(e as Map<String, dynamic>))
          .toList(),
      diagnosis: rawDiagnosis == null ? null : Diagnosis.fromJson(rawDiagnosis),
      diagnosisError: json['diagnosis_error'] as String?,
      ref: json['ref'] as String?,
      commitSha: json['commit_sha'] as String?,
    );
  }

  static AnalysisStatus _statusFrom(String? value) {
    switch (value) {
      case 'running':
        return AnalysisStatus.running;
      case 'completed':
        return AnalysisStatus.completed;
      case 'failed':
        return AnalysisStatus.failed;
      default:
        return AnalysisStatus.queued;
    }
  }
}


class FileSource {
  final String path;
  final String content;
  final int lines;

  const FileSource({
    required this.path,
    required this.content,
    required this.lines,
  });

  factory FileSource.fromJson(Map<String, dynamic> json) => FileSource(
        path: json['path'] as String? ?? '',
        content: json['content'] as String? ?? '',
        lines: json['lines'] as int? ?? 0,
      );
}

class Answer {
  final String question;
  final String answer;

  const Answer({required this.question, required this.answer});

  factory Answer.fromJson(Map<String, dynamic> json) => Answer(
        question: json['question'] as String? ?? '',
        answer: json['answer'] as String? ?? '',
      );
}

class PatchHunk {
  final int startLine;
  final int endLine;
  final String oldText;
  final String newText;

  const PatchHunk({
    required this.startLine,
    required this.endLine,
    required this.oldText,
    required this.newText,
  });

  factory PatchHunk.fromJson(Map<String, dynamic> json) => PatchHunk(
        startLine: json['start_line'] as int? ?? 0,
        endLine: json['end_line'] as int? ?? 0,
        oldText: json['old_text'] as String? ?? '',
        newText: json['new_text'] as String? ?? '',
      );
}

class PatchFile {
  final String path;
  final String language;
  final List<PatchHunk> hunks;

  const PatchFile({
    required this.path,
    this.language = '',
    this.hunks = const [],
  });

  String get fileName => path.split('/').last;

  factory PatchFile.fromJson(Map<String, dynamic> json) => PatchFile(
        path: json['path'] as String? ?? '',
        language: json['language'] as String? ?? '',
        hunks: (json['hunks'] as List<dynamic>? ?? [])
            .map((e) => PatchHunk.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

class PatchProposal {
  final String status;
  final String summary;
  final String reasoning;
  final double? confidence;
  final List<PatchFile> files;
  final List<String> warnings;
  final List<String> errors;

  const PatchProposal({
    required this.status,
    required this.summary,
    required this.reasoning,
    this.confidence,
    this.files = const [],
    this.warnings = const [],
    this.errors = const [],
  });

  bool get isOk => status == 'ok';

  bool get canValidate => isOk && files.isNotEmpty;

  String get confidencePercent {
    final value = confidence;
    if (value == null) return '';
    return '${(value * 100).round()}% confidence';
  }

  factory PatchProposal.fromJson(Map<String, dynamic> json) => PatchProposal(
        status: json['status'] as String? ?? '',
        summary: json['summary'] as String? ?? '',
        reasoning: json['reasoning'] as String? ?? '',
        confidence: (json['confidence'] as num?)?.toDouble(),
        files: (json['files'] as List<dynamic>? ?? [])
            .map((e) => PatchFile.fromJson(e as Map<String, dynamic>))
            .toList(),
        warnings: (json['warnings'] as List<dynamic>? ?? [])
            .map((e) => e.toString())
            .toList(),
        errors: (json['errors'] as List<dynamic>? ?? [])
            .map((e) => e.toString())
            .toList(),
      );
}

class ValidationCommandResult {
  final String name;
  final List<String> argv;
  final int? exitCode;
  final bool timedOut;
  final String stdout;
  final String stderr;
  final int durationMs;
  final bool passed;

  const ValidationCommandResult({
    required this.name,
    this.argv = const [],
    this.exitCode,
    this.timedOut = false,
    this.stdout = '',
    this.stderr = '',
    this.durationMs = 0,
    this.passed = true,
  });

  String get displayName {
    switch (name) {
      case 'pub_get':
        return 'flutter pub get';
      case 'analyze':
        return 'flutter analyze';
      case 'test':
        return 'flutter test';
      default:
        return argv.isNotEmpty ? argv.join(' ') : name;
    }
  }

  factory ValidationCommandResult.fromJson(Map<String, dynamic> json) {
    final timedOut = json['timed_out'] as bool? ?? false;
    final exitCode = json['exit_code'] as int?;
    final passedJson = json['passed'];
    return ValidationCommandResult(
      name: json['name'] as String? ?? '',
      argv: (json['argv'] as List<dynamic>? ?? [])
          .map((e) => e.toString())
          .toList(),
      exitCode: exitCode,
      timedOut: timedOut,
      stdout: json['stdout'] as String? ?? '',
      stderr: json['stderr'] as String? ?? '',
      durationMs: json['duration_ms'] as int? ?? 0,
      passed: passedJson is bool
          ? passedJson
          : !timedOut && (exitCode ?? 0) == 0,
    );
  }
}

class PatchValidationResult {
  final String status;
  final bool applied;
  final bool validationPassed;
  final List<String> errors;
  final List<String> warnings;
  final List<ValidationCommandResult> commands;
  final bool runnable;
  final String unavailableReason;

  const PatchValidationResult({
    required this.status,
    required this.applied,
    required this.validationPassed,
    this.errors = const [],
    this.warnings = const [],
    this.commands = const [],
    this.runnable = false,
    this.unavailableReason = '',
  });

  /// Real Flutter checks ran and passed. Apply-only is not success.
  bool get isPassed =>
      status == 'passed' && validationPassed && runnable;

  bool get isFailed =>
      status == 'apply_failed' ||
      status == 'validation_failed' ||
      status == 'proposal_invalid';

  bool get isUnavailable =>
      !isFailed && (status == 'passed' && !runnable);

  factory PatchValidationResult.fromJson(Map<String, dynamic> json) =>
      PatchValidationResult(
        status: json['status'] as String? ?? '',
        applied: json['applied'] as bool? ?? false,
        validationPassed: json['validation_passed'] as bool? ?? false,
        errors: (json['errors'] as List<dynamic>? ?? [])
            .map((e) => e.toString())
            .toList(),
        warnings: (json['warnings'] as List<dynamic>? ?? [])
            .map((e) => e.toString())
            .toList(),
        commands: (json['commands'] as List<dynamic>? ?? [])
            .map(
              (e) => ValidationCommandResult.fromJson(
                e as Map<String, dynamic>,
              ),
            )
            .toList(),
        runnable: json['runnable'] as bool? ?? false,
        unavailableReason: json['unavailable_reason'] as String? ?? '',
      );
}

class PatchApproval {
  final bool approved;
  final String approvedAt;
  final String commitSha;
  final String analysisId;

  const PatchApproval({
    required this.approved,
    required this.approvedAt,
    required this.commitSha,
    required this.analysisId,
  });

  factory PatchApproval.fromJson(Map<String, dynamic> json) => PatchApproval(
        approved: json['approved'] as bool? ?? false,
        approvedAt: json['approved_at'] as String? ?? '',
        commitSha: json['commit_sha'] as String? ?? '',
        analysisId: json['analysis_id'] as String? ?? '',
      );
}

class PatchDelivery {
  final String status;
  final String stage;
  final String? branch;
  final String? commitSha;
  final String? baseCommitSha;
  final int? prNumber;
  final String? prUrl;
  final bool draft;
  final List<String> errors;
  final List<String> warnings;

  const PatchDelivery({
    required this.status,
    required this.stage,
    this.branch,
    this.commitSha,
    this.baseCommitSha,
    this.prNumber,
    this.prUrl,
    this.draft = true,
    this.errors = const [],
    this.warnings = const [],
  });

  bool get isSucceeded =>
      status == 'succeeded' && prNumber != null && (prUrl ?? '').isNotEmpty;

  bool get isRunning => status == 'running';

  bool get isFailed => status == 'failed';

  String get stageLabel {
    switch (stage) {
      case 'preconditions':
        return 'Preconditions';
      case 'apply':
        return 'Apply patch';
      case 'commit':
        return 'Create commit';
      case 'push':
        return 'Push branch';
      case 'pull_request':
        return 'Open pull request';
      default:
        return stage;
    }
  }

  String get shortCommit {
    final sha = commitSha ?? baseCommitSha ?? '';
    if (sha.length <= 12) return sha;
    return sha.substring(0, 12);
  }

  factory PatchDelivery.fromJson(Map<String, dynamic> json) => PatchDelivery(
        status: json['status'] as String? ?? '',
        stage: json['stage'] as String? ?? '',
        branch: json['branch'] as String?,
        commitSha: json['commit_sha'] as String?,
        baseCommitSha: json['base_commit_sha'] as String?,
        prNumber: json['pr_number'] as int?,
        prUrl: json['pr_url'] as String?,
        draft: json['draft'] as bool? ?? true,
        errors: (json['errors'] as List<dynamic>? ?? [])
            .map((e) => e.toString())
            .toList(),
        warnings: (json['warnings'] as List<dynamic>? ?? [])
            .map((e) => e.toString())
            .toList(),
      );
}

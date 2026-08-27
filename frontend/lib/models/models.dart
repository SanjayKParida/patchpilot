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

  const Repository({
    required this.owner,
    required this.repo,
    required this.fullName,
    this.description,
    this.private = false,
  });

  factory Repository.fromJson(Map<String, dynamic> json) {
    return Repository(
      owner: json['owner'] as String? ?? '',
      repo: json['repo'] as String? ?? '',
      fullName: json['full_name'] as String? ?? '',
      description: json['description'] as String?,
      private: json['private'] as bool? ?? false,
    );
  }

  Map<String, dynamic> toJson() => {
        'owner': owner,
        'repo': repo,
        'full_name': fullName,
        'description': description,
        'private': private,
      };
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
  });

  bool get isTerminal =>
      status == AnalysisStatus.completed || status == AnalysisStatus.failed;

  /// Human-readable description of the current pipeline stage.
  String get stageLabel {
    switch (stage) {
      case 'fetching_issue':
        return 'Reading the issue';
      case 'extracting_signals':
        return 'Extracting signals';
      case 'fetching_source':
        return 'Downloading repository source';
      case 'analyzing_structure':
        return 'Mapping code structure';
      case 'collecting_evidence':
        return 'Collecting evidence';
      case 'ranking':
        return 'Ranking candidate files';
      case 'diagnosing':
        return 'Diagnosing root cause';
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

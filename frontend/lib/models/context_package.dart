// models/context_package.dart
//
// Typed data model for the Context stage. This is new, Context-specific
// model code — it does not duplicate or replace any existing PatchPilot
// model (Repository, Issue, etc. are assumed to already exist elsewhere
// and are imported by context_screen.dart, not redefined here).
//
// Field names follow the property list from the ContextPackage /
// ContextSlice spec (filePath, tier, tierCode, tierLabel, relevanceScore,
// reason, symbols, startLine, endLine, content, truncated, omitted,
// files, omittedFiles, warnings, budget, language, adapter). If the real
// backend contract differs in key casing or shape, only `fromJson` below
// needs to change — nothing in the UI layer depends on the wire format.

import 'package:flutter/foundation.dart';

/// The seven semantic context tiers produced by the backend ContextBuilder.
/// Fixed by the backend — do not add, remove, or reorder tiers here.
enum ContextTier {
  t0Defect,
  t1Supporting,
  t2Referenced,
  t3Callers,
  t4Contracts,
  t5Tests,
  t6Secondary;

  /// Short machine code, e.g. "T0".
  String get code {
    switch (this) {
      case ContextTier.t0Defect:
        return 'T0';
      case ContextTier.t1Supporting:
        return 'T1';
      case ContextTier.t2Referenced:
        return 'T2';
      case ContextTier.t3Callers:
        return 'T3';
      case ContextTier.t4Contracts:
        return 'T4';
      case ContextTier.t5Tests:
        return 'T5';
      case ContextTier.t6Secondary:
        return 'T6';
    }
  }

  /// Human-readable label, e.g. "Defect site".
  String get label {
    switch (this) {
      case ContextTier.t0Defect:
        return 'Defect site';
      case ContextTier.t1Supporting:
        return 'Supporting declarations';
      case ContextTier.t2Referenced:
        return 'Referenced types';
      case ContextTier.t3Callers:
        return 'Callers / dependents';
      case ContextTier.t4Contracts:
        return 'Contracts';
      case ContextTier.t5Tests:
        return 'Tests';
      case ContextTier.t6Secondary:
        return 'Secondary ranked files';
    }
  }

  static ContextTier fromCode(String? raw) {
    switch ((raw ?? '').trim().toUpperCase()) {
      case 'T0':
      case '0':
        return ContextTier.t0Defect;
      case 'T1':
      case '1':
        return ContextTier.t1Supporting;
      case 'T2':
      case '2':
        return ContextTier.t2Referenced;
      case 'T3':
      case '3':
        return ContextTier.t3Callers;
      case 'T4':
      case '4':
        return ContextTier.t4Contracts;
      case 'T5':
      case '5':
        return ContextTier.t5Tests;
      case 'T6':
      case '6':
        return ContextTier.t6Secondary;
      default:
        return ContextTier.t6Secondary;
    }
  }

  /// Backend slices carry a numeric tier 0–6; the UI spec also allows T0–T6.
  static ContextTier fromWire(dynamic raw) {
    if (raw is int) {
      switch (raw) {
        case 0:
          return ContextTier.t0Defect;
        case 1:
          return ContextTier.t1Supporting;
        case 2:
          return ContextTier.t2Referenced;
        case 3:
          return ContextTier.t3Callers;
        case 4:
          return ContextTier.t4Contracts;
        case 5:
          return ContextTier.t5Tests;
        case 6:
          return ContextTier.t6Secondary;
        default:
          return ContextTier.t6Secondary;
      }
    }
    if (raw is num) return fromWire(raw.toInt());
    return fromCode(raw?.toString());
  }
}

int? _readInt(dynamic value) {
  if (value == null) return null;
  if (value is int) return value;
  if (value is num) return value.toInt();
  return int.tryParse(value.toString());
}

int _readIntOrZero(dynamic value) => _readInt(value) ?? 0;

double? _readDouble(dynamic value) {
  if (value == null) return null;
  if (value is double) return value;
  if (value is num) return value.toDouble();
  return double.tryParse(value.toString());
}

String? _readString(dynamic value) {
  if (value == null) return null;
  final text = value.toString();
  return text.isEmpty ? null : text;
}

List<String> _readStringList(dynamic raw) {
  if (raw is! List) return const [];
  return raw.map((item) => item.toString()).toList();
}

/// Paths from either `["a.dart"]` or `[{"path": "a.dart", ...}]`.
List<String> _readPaths(dynamic raw) {
  if (raw is! List) return const [];
  return raw
      .map((item) {
        if (item is String) return item;
        if (item is Map) {
          return item['path']?.toString() ??
              item['filePath']?.toString() ??
              item['file_path']?.toString() ??
              '';
        }
        return item.toString();
      })
      .where((path) => path.isNotEmpty)
      .toList();
}

@immutable
class ContextSlice {
  final String filePath;
  final ContextTier tier;
  final double? relevanceScore;
  final String reason;
  final List<String> symbols;
  final int? startLine;
  final int? endLine;
  final String? content;
  final bool truncated;
  final bool omitted;

  const ContextSlice({
    required this.filePath,
    required this.tier,
    required this.reason,
    this.relevanceScore,
    this.symbols = const [],
    this.startLine,
    this.endLine,
    this.content,
    this.truncated = false,
    this.omitted = false,
  });

  bool get hasLineRange => startLine != null && endLine != null;

  String get lineRangeLabel =>
      hasLineRange ? 'lines $startLine–$endLine' : '';

  factory ContextSlice.fromJson(Map<String, dynamic> json) {
    final rawScore = json['relevanceScore'] ?? json['relevance_score'];
    return ContextSlice(
      filePath:
          json['filePath'] as String? ??
          json['file_path'] as String? ??
          json['path'] as String? ??
          '',
      tier: ContextTier.fromWire(
        json['tierCode'] ?? json['tier_code'] ?? json['tier'],
      ),
      relevanceScore: _readDouble(rawScore),
      reason: json['reason'] as String? ?? '',
      symbols:
          (json['symbols'] as List?)?.map((e) => e.toString()).toList() ??
          const [],
      startLine: _readInt(json['startLine'] ?? json['start_line']),
      endLine: _readInt(json['endLine'] ?? json['end_line']),
      content: json['content'] as String?,
      truncated: json['truncated'] as bool? ?? false,
      omitted: json['omitted'] as bool? ?? false,
    );
  }
}

@immutable
class ContextBudget {
  final int usedLines;
  final int maxLines;
  final int? estimatedTokens;

  const ContextBudget({
    required this.usedLines,
    required this.maxLines,
    this.estimatedTokens,
  });

  factory ContextBudget.fromJson(Map<String, dynamic> json) {
    return ContextBudget(
      usedLines: _readIntOrZero(
        json['usedLines'] ?? json['used_lines'] ?? json['lines_used'],
      ),
      maxLines: _readIntOrZero(
        json['maxLines'] ?? json['max_lines'] ?? json['max_lines_total'],
      ),
      estimatedTokens: _readInt(
        json['estimatedTokens'] ?? json['estimated_tokens'],
      ),
    );
  }
}

@immutable
class ContextPackage {
  final String issueId;
  final String? diagnosisSummary;
  final String? rootCause;
  final List<ContextSlice> slices;
  final List<String> files;
  final List<String> omittedFiles;
  final List<String> warnings;
  final ContextBudget budget;
  final String? language;
  final String? adapter;

  const ContextPackage({
    required this.issueId,
    required this.slices,
    required this.files,
    required this.budget,
    this.diagnosisSummary,
    this.rootCause,
    this.omittedFiles = const [],
    this.warnings = const [],
    this.language,
    this.adapter,
  });

  int get fileCount => files.length;
  bool get hasWarnings => warnings.isNotEmpty;

  factory ContextPackage.fromJson(Map<String, dynamic> json) {
    final issue = json['issue'];
    final diagnosis = json['diagnosis'];
    final rootCauseRaw = json['rootCause'] ?? json['root_cause'];

    return ContextPackage(
      issueId:
          json['issueId'] as String? ??
          json['issue_id'] as String? ??
          (issue is Map
              ? issue['number']?.toString() ?? issue['id']?.toString() ?? ''
              : ''),
      diagnosisSummary:
          json['diagnosisSummary'] as String? ??
          json['diagnosis_summary'] as String? ??
          (diagnosis is Map
              ? _readString(diagnosis['explanation'] ?? diagnosis['summary'])
              : null),
      rootCause: _readRootCause(rootCauseRaw, diagnosis),
      slices: (json['slices'] as List? ?? const [])
          .map((e) => ContextSlice.fromJson(e as Map<String, dynamic>))
          .toList(),
      files: _readPaths(json['files']),
      omittedFiles: _readPaths(
        json['omittedFiles'] ?? json['omitted_files'] ?? json['omitted'],
      ),
      warnings: _readStringList(json['warnings']),
      budget: ContextBudget.fromJson(
        (json['budget'] as Map<String, dynamic>?) ?? const <String, dynamic>{},
      ),
      language: json['language'] as String?,
      adapter: json['adapter'] as String?,
    );
  }
}

String? _readRootCause(dynamic rootCauseRaw, dynamic diagnosis) {
  if (rootCauseRaw is String && rootCauseRaw.isNotEmpty) return rootCauseRaw;
  if (rootCauseRaw is Map) {
    return _readString(
      rootCauseRaw['root_cause'] ??
          rootCauseRaw['symbol'] ??
          rootCauseRaw['summary'],
    );
  }
  if (diagnosis is Map) {
    return _readString(diagnosis['root_cause'] ?? diagnosis['rootCause']);
  }
  return null;
}

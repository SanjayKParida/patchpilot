import 'package:flutter_test/flutter_test.dart';

import 'package:patchpilot_web/models/models.dart';

/// "View root cause" must land on the defect.
///
/// The bug this guards against: using the first RELATED symbol the
/// model happened to mention — a type the defect merely refers to —
/// as if it were the defect site.

const _rootCause = SymbolLocation(
  symbol: '_applyFilter',
  path: 'lib/bloc/task_bloc.dart',
  line: 42,
  kind: 'function',
);

const _supporting = SymbolLocation(
  symbol: 'TaskFilter',
  path: 'lib/models/task_filter.dart',
  line: 1,
  kind: 'enum',
);

Diagnosis _diagnosis({
  List<SymbolLocation> rootCause = const [],
  List<SymbolLocation> supporting = const [],
  List<String> files = const ['lib/bloc/task_bloc.dart'],
}) {
  return Diagnosis(
    rootCause: 'Filter branch returns the wrong list.',
    confidence: 0.9,
    explanation: '...',
    suggestedFix: '...',
    citedFiles: files,
    locations: supporting,
    rootCauseLocations: rootCause,
  );
}

void main() {
  test('navigates to the root-cause symbol', () {
    final d = _diagnosis(
      rootCause: const [_rootCause],
      supporting: const [_supporting],
    );

    expect(d.rootCauseLocation?.symbol, '_applyFilter');
    expect(d.rootCauseLocation?.line, 42);
  });

  test('a supporting symbol is never used as the root cause', () {
    // The regression: supporting symbols present, root cause absent.
    final d = _diagnosis(supporting: const [_supporting]);

    expect(d.rootCauseLocation, isNull);
    expect(d.locations, isNotEmpty);
  });

  test('falls back to the affected file, not a related symbol', () {
    final d = _diagnosis(supporting: const [_supporting]);

    expect(d.rootCauseLocation, isNull);
    expect(d.affectedFile, 'lib/bloc/task_bloc.dart');
    expect(d.affectedFile, isNot(_supporting.path));
  });

  test('no cited files means no fallback target', () {
    final d = _diagnosis(files: const []);

    expect(d.rootCauseLocation, isNull);
    expect(d.affectedFile, isNull);
  });

  test('the first root-cause symbol wins when several resolve', () {
    final d = _diagnosis(
      rootCause: const [
        _rootCause,
        SymbolLocation(
          symbol: 'TaskBloc',
          path: 'lib/bloc/task_bloc.dart',
          line: 1,
          kind: 'class',
        ),
      ],
    );

    expect(d.rootCauseLocation?.symbol, '_applyFilter');
  });

  test('parses both location lists from the API', () {
    final d = Diagnosis.fromJson(const {
      'root_cause': 'x',
      'confidence': 0.8,
      'explanation': 'y',
      'suggested_fix': 'z',
      'relevant_files': ['lib/bloc/task_bloc.dart'],
      'root_cause_locations': [
        {
          'symbol': '_applyFilter',
          'path': 'lib/bloc/task_bloc.dart',
          'line': 42,
          'kind': 'function',
        }
      ],
      'locations': [
        {
          'symbol': 'TaskFilter',
          'path': 'lib/models/task_filter.dart',
          'line': 1,
          'kind': 'enum',
        }
      ],
    });

    expect(d.rootCauseLocation?.symbol, '_applyFilter');
    expect(d.locations.single.symbol, 'TaskFilter');
  });

  test('a diagnosis with neither list still parses', () {
    final d = Diagnosis.fromJson(const {
      'root_cause': 'x',
      'confidence': 0.5,
      'explanation': 'y',
      'suggested_fix': 'z',
      'relevant_files': <String>[],
    });

    expect(d.rootCauseLocation, isNull);
    expect(d.locations, isEmpty);
  });
}

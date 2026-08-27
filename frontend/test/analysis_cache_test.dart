import 'package:flutter_test/flutter_test.dart';

import 'package:patchpilot_web/models/models.dart';
import 'package:patchpilot_web/services/analysis_cache.dart';

/// An analysis costs a repository download and two paid model calls.
/// The cache exists so revisiting an issue does not pay that twice.

Analysis _analysis(
  AnalysisStatus status, {
  String id = 'a1',
}) {
  return Analysis(
    id: id,
    status: status,
    issueNumber: 1,
  );
}

const _key = 'owner/repo#1';

void main() {
  test('key is stable for the same issue', () {
    expect(
      AnalysisCache.keyFor('owner', 'repo', 1),
      AnalysisCache.keyFor('owner', 'repo', 1),
    );
    expect(
      AnalysisCache.keyFor('owner', 'repo', 1),
      isNot(AnalysisCache.keyFor('owner', 'repo', 2)),
    );
  });

  test('a completed analysis is returned instead of re-run', () {
    final cache = AnalysisCache();
    cache.save(_key, _analysis(AnalysisStatus.completed));

    expect(cache.read(_key)?.status, AnalysisStatus.completed);
  });

  test('an unseen issue is a miss', () {
    expect(AnalysisCache().read(_key), isNull);
  });

  test('a failed analysis is not cached, so reopening retries', () {
    final cache = AnalysisCache();
    cache.save(_key, _analysis(AnalysisStatus.failed));

    expect(cache.read(_key), isNull);
  });

  test('an in-flight analysis is not cached', () {
    final cache = AnalysisCache();
    cache.save(_key, _analysis(AnalysisStatus.running));
    cache.save(_key, _analysis(AnalysisStatus.queued));

    expect(cache.read(_key), isNull);
  });

  test('file source is reused per analysis', () {
    final cache = AnalysisCache();
    const file = FileSource(path: 'lib/a.dart', content: 'x', lines: 1);

    expect(cache.readFile('a1', 'lib/a.dart'), isNull);

    cache.saveFile('a1', file);

    expect(cache.readFile('a1', 'lib/a.dart')?.content, 'x');
    // A different analysis is a different snapshot.
    expect(cache.readFile('a2', 'lib/a.dart'), isNull);
  });

  test('invalidating drops the analysis and its cached source', () {
    final cache = AnalysisCache();
    cache.save(_key, _analysis(AnalysisStatus.completed, id: 'a1'));
    cache.saveFile(
      'a1',
      const FileSource(path: 'lib/a.dart', content: 'x', lines: 1),
    );

    cache.invalidate(_key);

    expect(cache.read(_key), isNull);
    expect(cache.readFile('a1', 'lib/a.dart'), isNull);
  });
}

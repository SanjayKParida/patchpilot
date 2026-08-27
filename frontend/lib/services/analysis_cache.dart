import '../models/models.dart';

/// Remembers completed analyses for the lifetime of the session.
///
/// An analysis downloads the repository's source and makes two paid
/// model calls. Re-running it because someone pressed back and then
/// opened the same issue again costs about forty seconds and real
/// money, and returns an answer that is not meaningfully different.
///
/// Only COMPLETED analyses are cached. A failed one is left out
/// deliberately so that reopening the issue retries rather than
/// showing a stale failure for the rest of the session.
class AnalysisCache {
  final Map<String, Analysis> _analyses = {};

  /// Source is cached per analysis, not globally: file contents belong
  /// to the snapshot that analysis ran against.
  final Map<String, FileSource> _files = {};

  static String keyFor(String owner, String repo, int issueNumber) =>
      '$owner/$repo#$issueNumber';

  // ---------------------------------------------------------
  // Analyses
  // ---------------------------------------------------------

  Analysis? read(String key) => _analyses[key];

  void save(String key, Analysis analysis) {
    if (analysis.status != AnalysisStatus.completed) return;
    _analyses[key] = analysis;
  }

  void invalidate(String key) {
    final analysis = _analyses.remove(key);
    if (analysis == null) return;

    _files.removeWhere(
      (fileKey, _) => fileKey.startsWith('${analysis.id}:'),
    );
  }

  // ---------------------------------------------------------
  // File sources
  // ---------------------------------------------------------

  FileSource? readFile(String analysisId, String path) =>
      _files['$analysisId:$path'];

  void saveFile(String analysisId, FileSource file) {
    _files['$analysisId:${file.path}'] = file;
  }
}

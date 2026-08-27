import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/models.dart';

/// Raised for any failed API call. Carries a message already fit to
/// show a user, because the API returns one in `detail`.
class ApiException implements Exception {
  final String message;
  final int? statusCode;

  const ApiException(this.message, {this.statusCode});

  @override
  String toString() => message;
}

class ApiClient {
  /// Overridable at build time:
  ///   flutter run -d chrome --dart-define=API_BASE_URL=http://host:8000
  static const String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://127.0.0.1:8000',
  );

  static const Duration _timeout = Duration(seconds: 30);

  final http.Client _http;

  ApiClient({http.Client? client}) : _http = client ?? http.Client();

  // ---------------------------------------------------------
  // Repositories
  // ---------------------------------------------------------

  Future<Repository> resolveRepository(String url) async {
    final json = await _get('/api/repositories', {'url': url});
    return Repository.fromJson(json as Map<String, dynamic>);
  }

  Future<List<Issue>> listIssues(
    String owner,
    String repo, {
    String? search,
  }) async {
    final hasSearch = search != null && search.isNotEmpty;

    final json = await _get(
      '/api/repositories/$owner/$repo/issues',
      hasSearch ? {'search': search} : null,
    );

    return (json as List<dynamic>)
        .map((e) => Issue.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  // ---------------------------------------------------------
  // Analyses
  // ---------------------------------------------------------

  Future<Analysis> startAnalysis({
    required String owner,
    required String repo,
    required int issueNumber,
  }) async {
    final json = await _post('/api/analyses', {
      'owner': owner,
      'repo': repo,
      'issue_number': issueNumber,
    });

    return Analysis.fromJson(json as Map<String, dynamic>);
  }

  Future<Analysis> getAnalysis(String id) async {
    final json = await _get('/api/analyses/$id', null);
    return Analysis.fromJson(json as Map<String, dynamic>);
  }

  /// Poll an analysis until it reaches a terminal state.
  ///
  /// Emits every update so the UI can show pipeline progress rather
  /// than an opaque spinner.
  Stream<Analysis> watchAnalysis(
    String id, {
    Duration interval = const Duration(milliseconds: 1200),
  }) async* {
    while (true) {
      final analysis = await getAnalysis(id);
      yield analysis;

      if (analysis.isTerminal) return;

      await Future<void>.delayed(interval);
    }
  }

  /// Source of one file the analysis ranked.
  Future<FileSource> getAnalysisFile(String id, String path) async {
    final json = await _get('/api/analyses/$id/files', {'path': path});
    return FileSource.fromJson(json as Map<String, dynamic>);
  }

  /// Ask one question about a completed analysis.
  Future<Answer> askQuestion(String id, String question) async {
    final json = await _post(
      '/api/analyses/$id/questions',
      {'question': question},
    );
    return Answer.fromJson(json as Map<String, dynamic>);
  }

  // ---------------------------------------------------------
  // Transport
  // ---------------------------------------------------------

  Future<dynamic> _get(String path, Map<String, String>? query) {
    final uri = Uri.parse('$baseUrl$path').replace(
      queryParameters: query,
    );

    return _send(() => _http.get(uri));
  }

  Future<dynamic> _post(String path, Map<String, dynamic> body) {
    final uri = Uri.parse('$baseUrl$path');

    return _send(
      () => _http.post(
        uri,
        headers: const {'Content-Type': 'application/json'},
        body: jsonEncode(body),
      ),
    );
  }

  Future<dynamic> _send(Future<http.Response> Function() request) async {
    http.Response response;

    try {
      response = await request().timeout(_timeout);
    } on TimeoutException {
      throw const ApiException('The API did not respond in time.');
    } catch (_) {
      throw const ApiException(
        'Could not reach the PatchPilot API. Is the backend running?',
      );
    }

    if (response.statusCode >= 400) {
      throw ApiException(
        _messageFrom(response),
        statusCode: response.statusCode,
      );
    }

    if (response.body.isEmpty) return null;

    return jsonDecode(response.body);
  }

  String _messageFrom(http.Response response) {
    try {
      final decoded = jsonDecode(response.body);

      if (decoded is Map<String, dynamic>) {
        final detail = decoded['detail'];
        if (detail is String && detail.isNotEmpty) return detail;
        // FastAPI validation errors arrive as a list.
        if (detail is List && detail.isNotEmpty) {
          return detail.first is Map
              ? (detail.first['msg']?.toString() ?? 'Invalid request.')
              : detail.first.toString();
        }
      }
    } catch (_) {
      // Fall through to the generic message below.
    }

    return 'Request failed (${response.statusCode}).';
  }
}

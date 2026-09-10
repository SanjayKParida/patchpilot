import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/context_package.dart';
import '../models/models.dart';
import 'api_http.dart';
import 'key_value_store.dart';
import 'session_token.dart';

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
    defaultValue: 'http://localhost:8000',
  );

  static const Duration _timeout = Duration(seconds: 30);

  /// Patch generation can wait on a slow model call. Match validate/deliver.
  static const Duration patchGenerateTimeout = Duration(seconds: 180);

  static const Duration snapshotPrepareTimeout = Duration(seconds: 180);

  static const Duration _patchPollInterval = Duration(milliseconds: 400);

  final http.Client _http;
  final KeyValueStore _tokens;

  ApiClient({http.Client? client, KeyValueStore? tokens})
    : _http = client ?? createApiHttpClient(),
      _tokens = tokens ?? KeyValueStore();

  void storeSessionToken(String sessionId) {
    _tokens.write(sessionStorageKey, sessionId);
  }

  void clearSessionToken() {
    _tokens.remove(sessionStorageKey);
  }

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

  Future<Repository> getDemoRepository() async {
    final json = await _get('/api/repositories/demo', null);
    return Repository.fromJson(json as Map<String, dynamic>);
  }

  Future<List<Repository>> listAuthorizedRepositories() async {
    final json = await _get('/api/repositories/authorized', null);
    return (json as List<dynamic>)
        .map((e) => Repository.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<List<Repository>> refreshAuthorizedRepositories() async {
    final json = await _post('/api/repositories/authorized/refresh', {});
    return (json as List<dynamic>)
        .map((e) => Repository.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<RepositorySnapshot> prepareRepositorySnapshot(
    String owner,
    String repo, {
    String? ref,
    Duration? timeout,
    Duration? pollInterval,
  }) async {
    final wait = timeout ?? snapshotPrepareTimeout;
    final interval = pollInterval ?? _patchPollInterval;
    final query = _refQuery(ref);

    try {
      final json = await _post(
        '/api/repositories/$owner/$repo/snapshot',
        {},
        timeout: wait,
        query: query,
      );
      return RepositorySnapshot.fromJson(json as Map<String, dynamic>);
    } on ApiException catch (e) {
      if (e.statusCode == 409) {
        return _pollRepositorySnapshot(
          owner,
          repo,
          ref: ref,
          budget: wait,
          interval: interval,
        );
      }
      rethrow;
    }
  }

  Future<RepositorySnapshot> getRepositorySnapshot(
    String owner,
    String repo, {
    String? ref,
  }) async {
    final json = await _get(
      '/api/repositories/$owner/$repo/snapshot',
      _refQuery(ref),
    );
    return RepositorySnapshot.fromJson(json as Map<String, dynamic>);
  }

  Map<String, String>? _refQuery(String? ref) {
    final pinned = ref?.trim();
    if (pinned == null || pinned.isEmpty) return null;
    return {'ref': pinned};
  }

  Future<RepositorySnapshot> _pollRepositorySnapshot(
    String owner,
    String repo, {
    String? ref,
    required Duration budget,
    required Duration interval,
  }) async {
    final deadline = DateTime.now().add(budget);

    while (true) {
      final current = await getRepositorySnapshot(owner, repo, ref: ref);
      if (current.isReady) return current;
      if (!DateTime.now().isBefore(deadline)) {
        throw const ApiException('The API did not respond in time.');
      }
      await Future<void>.delayed(interval);
    }
  }

  // ---------------------------------------------------------
  // Auth
  // ---------------------------------------------------------

  Future<AuthMe> getMe() async {
    final json = await _get('/api/auth/me', null);
    return AuthMe.fromJson(json as Map<String, dynamic>);
  }

  Future<String> startGithubLogin({
    String? returnTo,
    String? analysisId,
    String? stage,
    String? repairPath,
  }) async {
    final query = <String, String>{};
    if (returnTo != null && returnTo.isNotEmpty) {
      query['return_to'] = returnTo;
    }
    if (analysisId != null && analysisId.isNotEmpty) {
      query['analysis_id'] = analysisId;
    }
    if (stage != null && stage.isNotEmpty) {
      query['stage'] = stage;
    }
    if (repairPath != null && repairPath.isNotEmpty) {
      query['repair_path'] = repairPath;
    }
    final json = await _get(
      '/api/auth/github/login',
      query.isEmpty ? null : query,
    );
    final map = json as Map<String, dynamic>;
    return map['authorization_url'] as String? ?? '';
  }

  Future<String> startGithubInstall({String? returnTo}) async {
    final json = await _get(
      '/api/auth/github/install',
      returnTo == null || returnTo.isEmpty ? null : {'return_to': returnTo},
    );
    final map = json as Map<String, dynamic>;
    return map['installation_url'] as String? ?? '';
  }

  Future<void> logout() async {
    try {
      await _post('/api/auth/logout', {});
    } finally {
      clearSessionToken();
    }
  }

  // ---------------------------------------------------------
  // Analyses
  // ---------------------------------------------------------

  Future<Analysis> startAnalysis({
    required String owner,
    required String repo,
    required int issueNumber,
    String? ref,
    bool force = false,
  }) async {
    final body = <String, dynamic>{
      'owner': owner,
      'repo': repo,
      'issue_number': issueNumber,
    };
    final pinned = ref?.trim();
    if (pinned != null && pinned.isNotEmpty) {
      body['ref'] = pinned;
    }
    if (force) {
      body['force'] = true;
    }

    final json = await _post('/api/analyses', body);

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

  /// Bounded context for a completed analysis.
  ///
  /// Served from GET /analyses/{id}/context — slice content is kept off
  /// the polling Analysis payload.
  Future<ContextPackage> getContextPackage(String analysisId) async {
    final json = await _get('/api/analyses/$analysisId/context', null);
    return ContextPackage.fromJson(json as Map<String, dynamic>);
  }

  /// Ask one question about a completed analysis.
  Future<Answer> askQuestion(String id, String question) async {
    final json = await _post('/api/analyses/$id/questions', {
      'question': question,
    });
    return Answer.fromJson(json as Map<String, dynamic>);
  }

  // ---------------------------------------------------------
  // Patch review
  // ---------------------------------------------------------

  Future<PatchProposal> generatePatch(
    String id, {
    Duration? timeout,
    Duration? pollInterval,
  }) async {
    final wait = timeout ?? patchGenerateTimeout;
    final interval = pollInterval ?? _patchPollInterval;

    try {
      final json = await _post('/api/analyses/$id/patch', {}, timeout: wait);
      return PatchProposal.fromJson(json as Map<String, dynamic>);
    } on ApiException catch (e) {
      if (e.statusCode == 409 || _isTimeout(e) || _isUnreachable(e)) {
        return _pollPatch(id, wait, interval);
      }
      rethrow;
    }
  }

  Future<PatchProposal> _pollPatch(
    String id,
    Duration budget,
    Duration interval,
  ) async {
    final deadline = DateTime.now().add(budget);

    while (true) {
      try {
        return await getPatch(id);
      } on ApiException catch (e) {
        if (e.statusCode != 409 && !_isTimeout(e) && !_isUnreachable(e)) {
          rethrow;
        }
        if (!DateTime.now().isBefore(deadline)) {
          throw const ApiException('The API did not respond in time.');
        }
        await Future<void>.delayed(interval);
      }
    }
  }

  bool _isTimeout(ApiException error) {
    return error.message == 'The API did not respond in time.';
  }

  bool _isUnreachable(ApiException error) {
    return error.message.contains('Could not reach the PatchPilot API');
  }

  Future<PatchProposal> getPatch(String id) async {
    final json = await _get('/api/analyses/$id/patch', null);
    return PatchProposal.fromJson(json as Map<String, dynamic>);
  }

  Future<PatchValidationResult> validatePatch(String id) async {
    final json = await _post(
      '/api/analyses/$id/patch/validate',
      {},
      timeout: const Duration(seconds: 180),
    );
    return PatchValidationResult.fromJson(json as Map<String, dynamic>);
  }

  Future<PatchValidationResult> getPatchValidation(String id) async {
    final json = await _get('/api/analyses/$id/patch/validate', null);
    return PatchValidationResult.fromJson(json as Map<String, dynamic>);
  }

  Future<PatchApproval> approvePatch(String id) async {
    final json = await _post('/api/analyses/$id/patch/approve', {});
    return PatchApproval.fromJson(json as Map<String, dynamic>);
  }

  Future<PatchApproval> getPatchApproval(String id) async {
    final json = await _get('/api/analyses/$id/patch/approve', null);
    return PatchApproval.fromJson(json as Map<String, dynamic>);
  }

  Future<PatchDelivery> deliverPatch(
    String id, {
    String? title,
    String? description,
  }) async {
    final body = <String, dynamic>{};
    final trimmedTitle = title?.trim() ?? '';
    final trimmedDescription = description?.trim() ?? '';
    if (trimmedTitle.isNotEmpty) body['title'] = trimmedTitle;
    if (trimmedDescription.isNotEmpty) {
      body['description'] = trimmedDescription;
    }
    final json = await _post(
      '/api/analyses/$id/patch/deliver',
      body,
      timeout: const Duration(seconds: 180),
    );
    return PatchDelivery.fromJson(json as Map<String, dynamic>);
  }

  Future<PatchDelivery> getPatchDelivery(String id) async {
    final json = await _get('/api/analyses/$id/patch/deliver', null);
    return PatchDelivery.fromJson(json as Map<String, dynamic>);
  }

  // ---------------------------------------------------------
  // Transport
  // ---------------------------------------------------------

  Future<dynamic> _get(
    String path,
    Map<String, String>? query, {
    Duration? timeout,
  }) {
    final uri = Uri.parse('$baseUrl$path').replace(queryParameters: query);

    return _send(
      () => _http.get(uri, headers: _authHeaders()),
      timeout: timeout,
    );
  }

  Future<dynamic> _post(
    String path,
    Map<String, dynamic> body, {
    Duration? timeout,
    Map<String, String>? query,
  }) {
    final uri = Uri.parse('$baseUrl$path').replace(queryParameters: query);

    return _send(
      () => _http.post(
        uri,
        headers: _authHeaders({'Content-Type': 'application/json'}),
        body: jsonEncode(body),
      ),
      timeout: timeout,
    );
  }

  Future<dynamic> _send(
    Future<http.Response> Function() request, {
    Duration? timeout,
  }) async {
    http.Response response;

    try {
      response = await request().timeout(timeout ?? _timeout);
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

    try {
      return jsonDecode(response.body);
    } catch (_) {
      throw const ApiException('The API returned an unexpected response.');
    }
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

  Map<String, String> _authHeaders([Map<String, String>? extra]) {
    final headers = <String, String>{...?extra};
    final token = _tokens.read(sessionStorageKey);
    if (token != null && token.isNotEmpty) {
      headers['Authorization'] = 'Bearer $token';
    }
    return headers;
  }
}

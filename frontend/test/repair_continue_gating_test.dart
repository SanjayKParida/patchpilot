import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/features/repair/shell/repair_session.dart';
import 'package:patchpilot_web/models/models.dart';
import 'package:patchpilot_web/services/analysis_cache.dart';
import 'package:patchpilot_web/services/api_client.dart';

const _path = 'lib/bloc/task_bloc.dart';

const _repo = Repository(owner: 'owner', repo: 'repo', fullName: 'owner/repo');

const _issue = Issue(
  number: 1,
  title: 'Refresh spinner never stops',
  body: 'Pull to refresh stays on TaskLoading.',
);

Analysis _completedAnalysis() {
  return Analysis(
    id: 'a1',
    status: AnalysisStatus.completed,
    issueNumber: 1,
    issue: _issue,
    diagnosis: const Diagnosis(
      rootCause: 'TaskBloc never emits TaskLoaded on refresh.',
      confidence: 0.9,
      explanation: 'The refresh handler stops in TaskLoading.',
      suggestedFix: 'Emit TaskLoaded after the refresh fetch succeeds.',
      citedFiles: [_path],
      rootCauseLocations: [],
    ),
    commitSha: 'f0bfc5b317f4984dc2c8d253715e9a30c72c0a5c',
  );
}

Map<String, dynamic> _analysisJson({
  String status = 'completed',
  String? stage,
  String? error,
  bool diagnosis = true,
}) {
  return {
    'id': 'a1',
    'status': status,
    if (stage != null) 'stage': stage,
    if (error != null) 'error': error,
    'issue_number': 1,
    if (diagnosis)
      'diagnosis': {
        'root_cause': 'TaskBloc never emits TaskLoaded on refresh.',
        'confidence': 0.9,
        'explanation': 'The refresh handler stops in TaskLoading.',
        'suggested_fix': 'Emit TaskLoaded after the refresh fetch succeeds.',
        'cited_files': [_path],
      },
  };
}

Map<String, dynamic> _patchJson({
  String status = 'ok',
  String summary = 'fix refresh',
  List<Map<String, dynamic>>? files,
}) {
  return {
    'status': status,
    'summary': summary,
    'reasoning': 'emit loaded',
    'confidence': 0.9,
    'files': files ??
        [
          {
            'path': _path,
            'language': 'dart',
            'hunks': [
              {
                'start_line': 1,
                'end_line': 1,
                'old_text': 'a',
                'new_text': 'b',
              },
            ],
          },
        ],
    'warnings': [],
    'errors': status == 'ok' ? [] : ['could not patch'],
  };
}

Map<String, dynamic> _validationJson({String status = 'passed'}) {
  return {
    'status': status,
    'applied': status != 'unavailable',
    'validation_passed': status == 'passed',
    'errors': status == 'failed' ? ['flutter analyze failed'] : [],
    'warnings': [],
    'commands': [
      {
        'name': 'analyze',
        'argv': ['flutter', 'analyze'],
        'exit_code': status == 'passed' ? 0 : 1,
        'timed_out': false,
        'stdout': '',
        'stderr': status == 'failed' ? 'error' : '',
        'duration_ms': 10,
        'passed': status == 'passed',
      },
    ],
    'runnable': true,
    'unavailable_reason': '',
  };
}

Map<String, dynamic> _approvalJson() => {
  'approved': true,
  'approved_at': '2026-08-30T12:00:00+00:00',
  'commit_sha': 'f0bfc5b317f4984dc2c8d253715e9a30c72c0a5c',
  'analysis_id': 'a1',
};

http.Response _json(Object body, [int status = 200]) {
  return http.Response(
    jsonEncode(body),
    status,
    headers: const {'content-type': 'application/json; charset=utf-8'},
  );
}

http.Response _missing([String detail = 'missing']) =>
    _json({'detail': detail}, 502);

Future<void> _pumpSession(
  WidgetTester tester, {
  required ApiClient api,
  AnalysisCache? cache,
}) async {
  tester.view.physicalSize = const Size(1200, 2400);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);

  final analysisCache = cache ?? AnalysisCache();
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.build(),
      home: RepairSession(
        api: api,
        cache: analysisCache,
        repository: _repo,
        issue: _issue,
        onBack: () {},
      ),
    ),
  );
}

ApiClient _client(Future<http.Response> Function(http.Request) handler) {
  return ApiClient(client: MockClient(handler));
}

bool _isPatch(Uri url) {
  final path = url.path;
  return path.endsWith('/patch') &&
      !path.contains('/patch/') &&
      !path.endsWith('/validate') &&
      !path.endsWith('/approve') &&
      !path.endsWith('/deliver');
}

Future<http.Response> _context(_) async {
  return _json({
    'issue_id': '1',
    'slices': [],
    'files': [],
    'budget': {'used_lines': 0, 'max_lines': 400},
  });
}

void main() {
  testWidgets('diagnosis loading keeps Continue disabled', (tester) async {
    final running = Completer<http.Response>();
    var gets = 0;
    final api = _client((request) async {
      final path = request.url.path;
      if (request.method == 'POST' && path.endsWith('/analyses')) {
        return _json({'id': 'a1', 'status': 'queued', 'issue_number': 1});
      }
      if (request.method == 'GET' && path.endsWith('/analyses/a1')) {
        gets += 1;
        if (gets == 1) {
          return _json(_analysisJson(status: 'running', stage: 'diagnosing'));
        }
        return running.future;
      }
      if (path.endsWith('/context')) return _context(request);
      return _missing();
    });

    await _pumpSession(tester, api: api);
    await tester.pump();
    await tester.pump();

    expect(find.text('Continue to Patch'), findsNothing);

    running.complete(_json(_analysisJson()));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 1200));
    await tester.pump();
    await tester.pump();

    expect(find.text('Continue to Patch'), findsOneWidget);
  });

  testWidgets('failed diagnosis does not enable Continue', (tester) async {
    final api = _client((request) async {
      final path = request.url.path;
      if (request.method == 'POST' && path.endsWith('/analyses')) {
        return _json({'id': 'a1', 'status': 'queued', 'issue_number': 1});
      }
      if (request.method == 'GET' && path.endsWith('/analyses/a1')) {
        return _json(
          _analysisJson(
            status: 'failed',
            error: 'model unavailable',
            diagnosis: false,
          ),
        );
      }
      return _missing();
    });

    await _pumpSession(tester, api: api);
    await tester.pump();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 1200));
    await tester.pump();
    await tester.pump();

    expect(find.text('Continue to Patch'), findsNothing);
    expect(find.text('Continue to Validation'), findsNothing);
  });

  testWidgets('patch cached load in flight keeps Continue disabled', (
    tester,
  ) async {
    final cache = AnalysisCache();
    cache.save(
      AnalysisCache.keyFor(_repo.owner, _repo.repo, _issue.number),
      _completedAnalysis(),
    );

    var patchGets = 0;
    final secondPatch = Completer<http.Response>();
    final api = _client((request) async {
      final path = request.url.path;
      if (_isPatch(request.url)) {
        patchGets += 1;
        if (patchGets == 1) return _json(_patchJson());
        return secondPatch.future;
      }
      if (path.endsWith('/context')) return _context(request);
      return _missing();
    });

    await _pumpSession(tester, api: api, cache: cache);
    await tester.pumpAndSettle();

    expect(find.text('Continue to Patch'), findsOneWidget);

    await tester.tap(find.text('Patch'));
    await tester.pump();
    await tester.pump();

    expect(find.text('Continue to Validation'), findsNothing);

    secondPatch.complete(_json(_patchJson()));
    await tester.pumpAndSettle();

    expect(find.text('Continue to Validation'), findsOneWidget);
  });

  testWidgets('patch generate in flight keeps Continue disabled', (
    tester,
  ) async {
    final cache = AnalysisCache();
    cache.save(
      AnalysisCache.keyFor(_repo.owner, _repo.repo, _issue.number),
      _completedAnalysis(),
    );

    final generate = Completer<http.Response>();
    final api = _client((request) async {
      final path = request.url.path;
      if (request.method == 'POST' && _isPatch(request.url)) {
        return generate.future;
      }
      if (path.endsWith('/context')) return _context(request);
      return _missing();
    });

    await _pumpSession(tester, api: api, cache: cache);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Patch'));
    await tester.pumpAndSettle();

    expect(find.text('Generate patch'), findsOneWidget);
    expect(find.text('Continue to Validation'), findsNothing);

    await tester.tap(find.text('Generate patch'));
    await tester.pump();
    await tester.pump();

    expect(find.text('Continue to Validation'), findsNothing);

    generate.complete(_json(_patchJson()));
    await tester.pumpAndSettle();

    expect(find.text('Continue to Validation'), findsOneWidget);
  });

  testWidgets('failed patch generation does not enable Continue', (
    tester,
  ) async {
    final cache = AnalysisCache();
    cache.save(
      AnalysisCache.keyFor(_repo.owner, _repo.repo, _issue.number),
      _completedAnalysis(),
    );

    final api = _client((request) async {
      final path = request.url.path;
      if (request.method == 'POST' && _isPatch(request.url)) {
        return _json({'detail': 'Patch generation failed'}, 502);
      }
      if (path.endsWith('/context')) return _context(request);
      return _missing();
    });

    await _pumpSession(tester, api: api, cache: cache);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Patch'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Generate patch'));
    await tester.pumpAndSettle();

    expect(find.text('Continue to Validation'), findsNothing);
    expect(find.text('Patch request failed'), findsOneWidget);
  });

  testWidgets('empty patch proposal does not enable Continue', (tester) async {
    final cache = AnalysisCache();
    cache.save(
      AnalysisCache.keyFor(_repo.owner, _repo.repo, _issue.number),
      _completedAnalysis(),
    );

    final api = _client((request) async {
      if (_isPatch(request.url)) {
        return _json(_patchJson(status: 'empty', files: const []));
      }
      if (request.url.path.endsWith('/context')) return _context(request);
      return _missing();
    });

    await _pumpSession(tester, api: api, cache: cache);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Patch'));
    await tester.pumpAndSettle();

    expect(find.text('Continue to Validation'), findsNothing);
  });

  testWidgets('validation loading keeps Continue disabled', (tester) async {
    final cache = AnalysisCache();
    cache.save(
      AnalysisCache.keyFor(_repo.owner, _repo.repo, _issue.number),
      _completedAnalysis(),
    );

    var validateGets = 0;
    final secondValidate = Completer<http.Response>();
    final api = _client((request) async {
      final path = request.url.path;
      if (_isPatch(request.url)) return _json(_patchJson());
      if (path.endsWith('/patch/validate')) {
        if (request.method == 'GET') {
          validateGets += 1;
          // 1 = RepairSession hydrate, 2 = PatchPanel cache load.
          if (validateGets <= 2) return _json(_validationJson());
          return secondValidate.future;
        }
        return _json(_validationJson());
      }
      if (path.endsWith('/context')) return _context(request);
      return _missing();
    });

    await _pumpSession(tester, api: api, cache: cache);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Patch'));
    await tester.pumpAndSettle();

    expect(find.text('Continue to Validation'), findsOneWidget);
    await tester.tap(find.text('Continue to Validation'));
    await tester.pump();
    await tester.pump();

    expect(find.text('Continue to Review'), findsNothing);

    secondValidate.complete(_json(_validationJson()));
    await tester.pumpAndSettle();

    expect(find.text('Continue to Review'), findsOneWidget);
  });

  testWidgets('failed validation does not enable Continue', (tester) async {
    final cache = AnalysisCache();
    cache.save(
      AnalysisCache.keyFor(_repo.owner, _repo.repo, _issue.number),
      _completedAnalysis(),
    );

    final api = _client((request) async {
      final path = request.url.path;
      if (_isPatch(request.url)) return _json(_patchJson());
      if (path.endsWith('/patch/validate')) {
        return _json(_validationJson(status: 'failed'));
      }
      if (path.endsWith('/context')) return _context(request);
      return _missing();
    });

    await _pumpSession(tester, api: api, cache: cache);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Patch'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Continue to Validation'));
    await tester.pumpAndSettle();

    expect(find.text('Continue to Review'), findsNothing);
    await tester.tap(find.text('Review'));
    await tester.pump();
    expect(
      find.text('Validation must pass before opening Review.'),
      findsOneWidget,
    );
  });

  testWidgets('approve in flight keeps Continue disabled', (tester) async {
    final cache = AnalysisCache();
    cache.save(
      AnalysisCache.keyFor(_repo.owner, _repo.repo, _issue.number),
      _completedAnalysis(),
    );

    final approve = Completer<http.Response>();
    final api = _client((request) async {
      final path = request.url.path;
      if (_isPatch(request.url)) return _json(_patchJson());
      if (path.endsWith('/patch/validate')) {
        return _json(_validationJson());
      }
      if (path.endsWith('/patch/approve')) {
        if (request.method == 'POST') return approve.future;
        return _missing('This patch has not been approved');
      }
      if (path.endsWith('/context')) return _context(request);
      return _missing();
    });

    await _pumpSession(tester, api: api, cache: cache);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Review'));
    await tester.pumpAndSettle();

    expect(find.text('Continue to Pull Request'), findsNothing);

    await tester.ensureVisible(
      find.widgetWithText(FilledButton, 'Approve patch'),
    );
    await tester.tap(find.widgetWithText(FilledButton, 'Approve patch'));
    await tester.pump();
    await tester.pump();

    expect(find.text('Continue to Pull Request'), findsNothing);

    approve.complete(_json(_approvalJson()));
    await tester.pumpAndSettle();

    expect(find.text('Continue to Pull Request'), findsOneWidget);
  });

  testWidgets('failed approve does not enable Continue', (tester) async {
    final cache = AnalysisCache();
    cache.save(
      AnalysisCache.keyFor(_repo.owner, _repo.repo, _issue.number),
      _completedAnalysis(),
    );

    final api = _client((request) async {
      final path = request.url.path;
      if (_isPatch(request.url)) return _json(_patchJson());
      if (path.endsWith('/patch/validate')) {
        return _json(_validationJson());
      }
      if (path.endsWith('/patch/approve')) {
        if (request.method == 'POST') {
          return _json({'detail': 'approve failed'}, 502);
        }
        return _missing('This patch has not been approved');
      }
      if (path.endsWith('/context')) return _context(request);
      return _missing();
    });

    await _pumpSession(tester, api: api, cache: cache);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Review'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(
      find.widgetWithText(FilledButton, 'Approve patch'),
    );
    await tester.tap(find.widgetWithText(FilledButton, 'Approve patch'));
    await tester.pumpAndSettle();

    expect(find.text('Continue to Pull Request'), findsNothing);
  });

  testWidgets('Pull Request never shows a Continue CTA', (tester) async {
    final cache = AnalysisCache();
    cache.save(
      AnalysisCache.keyFor(_repo.owner, _repo.repo, _issue.number),
      _completedAnalysis(),
    );

    final api = _client((request) async {
      final path = request.url.path;
      if (_isPatch(request.url)) return _json(_patchJson());
      if (path.endsWith('/patch/validate')) {
        return _json(_validationJson());
      }
      if (path.endsWith('/patch/approve')) {
        return _json(_approvalJson());
      }
      if (path.endsWith('/context')) return _context(request);
      return _missing();
    });

    await _pumpSession(tester, api: api, cache: cache);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Pull Request'));
    await tester.pumpAndSettle();

    expect(find.textContaining('Continue to'), findsNothing);
    expect(find.text('Create pull request'), findsOneWidget);
  });

  testWidgets('stage gating still blocks Validation without a patch', (
    tester,
  ) async {
    final cache = AnalysisCache();
    cache.save(
      AnalysisCache.keyFor(_repo.owner, _repo.repo, _issue.number),
      _completedAnalysis(),
    );

    final api = _client((request) async {
      if (request.url.path.endsWith('/context')) return _context(request);
      return _missing();
    });

    await _pumpSession(tester, api: api, cache: cache);
    await tester.pumpAndSettle();

    expect(find.text('Continue to Patch'), findsOneWidget);
    expect(find.text('Continue to Validation'), findsNothing);

    await tester.tap(find.text('Validation'));
    await tester.pump();

    expect(
      find.text('Generate a patch before opening Validation.'),
      findsOneWidget,
    );
  });
}

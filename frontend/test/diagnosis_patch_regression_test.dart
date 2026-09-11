import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:patchpilot_web/app/app_routes.dart';
import 'package:patchpilot_web/models/models.dart';
import 'package:patchpilot_web/features/repair/code_viewer/screens/code_viewer_screen.dart';
import 'package:patchpilot_web/features/repair/context/screens/context_screen.dart';
import 'package:patchpilot_web/features/repair/diagnosis/screens/diagnosis_screen.dart';
import 'package:patchpilot_web/features/repair/shell/repair_session.dart';
import 'package:patchpilot_web/features/repair/shell/repair_shell.dart';
import 'package:patchpilot_web/features/repair/shell/repair_workflow.dart';
import 'package:patchpilot_web/services/analysis_cache.dart';
import 'package:patchpilot_web/services/api_client.dart';
import 'package:patchpilot_web/services/github_redirect.dart';
import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/core/widgets/motion.dart';
import 'package:patchpilot_web/features/repair/diagnosis/widgets/explanation_section.dart';
import 'package:patchpilot_web/features/repair/diagnosis/widgets/follow_up.dart';
import 'package:patchpilot_web/features/repair/diagnosis/widgets/relevant_files_section.dart';
import 'package:patchpilot_web/features/repair/diagnosis/widgets/root_cause_section.dart';
import 'package:patchpilot_web/features/repair/patch/widgets/patch_panel.dart';
import 'package:patchpilot_web/features/repair/review/screens/review_screen.dart';
import 'package:patchpilot_web/features/repair/pull_request/screens/pull_request_screen.dart';
import 'package:patchpilot_web/features/repair/validation/screens/validation_screen.dart';

const _path = 'lib/bloc/task_bloc.dart';

class _TestRedirect implements GithubRedirect {
  String? opened;

  @override
  void go(String url) {}

  @override
  void open(String url) => opened = url;
}

Analysis _staleAnalysis() {
  return Analysis(
    id: 'stale',
    status: AnalysisStatus.completed,
    issueNumber: 1,
    issue: const Issue(
      number: 1,
      title: 'Refresh spinner never stops',
      body: 'Pull to refresh stays on TaskLoading.',
    ),
    signals: const [Signal(term: 'refresh', type: 'behavior')],
    relevantFiles: const [],
    diagnosis: const Diagnosis(
      rootCause: 'Stale cached root cause.',
      confidence: 0.5,
      explanation: 'This result is from an earlier local cache.',
      suggestedFix: 'Ignore this cached diagnosis.',
      citedFiles: [_path],
      rootCauseLocations: [],
    ),
    commitSha: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
  );
}

Analysis _completedAnalysis() {
  return Analysis(
    id: 'a1',
    status: AnalysisStatus.completed,
    issueNumber: 1,
    issue: const Issue(
      number: 1,
      title: 'Refresh spinner never stops',
      body: 'Pull to refresh stays on TaskLoading.',
    ),
    signals: const [Signal(term: 'refresh', type: 'behavior')],
    relevantFiles: const [
      RelevantFile(
        rank: 1,
        path: _path,
        totalScore: 4.2,
        signalsMatched: 1,
        evidence: [
          EvidenceItem(
            concept: 'refresh',
            kind: 'behavior_flow',
            identifier: 'TaskLoading',
            line: 12,
          ),
        ],
        structural: [],
      ),
    ],
    diagnosis: const Diagnosis(
      rootCause: 'TaskBloc never emits TaskLoaded on refresh.',
      confidence: 0.9,
      explanation: 'The refresh handler stops in TaskLoading.',
      suggestedFix: 'Emit TaskLoaded after the refresh fetch succeeds.',
      citedFiles: [_path],
      rootCauseLocations: [
        SymbolLocation(symbol: 'TaskBloc', path: _path, line: 1, kind: 'class'),
      ],
    ),
    commitSha: 'f0bfc5b317f4984dc2c8d253715e9a30c72c0a5c',
  );
}

Map<String, dynamic> _completedAnalysisJson() => {
  'id': 'a1',
  'status': 'completed',
  'issue_number': 1,
  'diagnosis': {
    'root_cause': 'TaskBloc never emits TaskLoaded on refresh.',
    'confidence': 0.9,
    'explanation': 'The refresh handler stops in TaskLoading.',
    'suggested_fix': 'Emit TaskLoaded after the refresh fetch succeeds.',
    'cited_files': [_path],
  },
};

const _repo = Repository(owner: 'owner', repo: 'repo', fullName: 'owner/repo');

const _demoRepo = Repository(
  owner: 'SanjayKParida',
  repo: 'patchpilot-diagnosis-demo',
  fullName: 'SanjayKParida/patchpilot-diagnosis-demo',
  demo: true,
);

const _issue = Issue(
  number: 1,
  title: 'Refresh spinner never stops',
  body: 'Pull to refresh stays on TaskLoading.',
);

ApiClient _api() {
  return ApiClient(
    client: MockClient((request) async {
      if (request.url.path.endsWith('/context')) {
        return http.Response(
          jsonEncode({
            'issue_id': '1',
            'slices': [
              {
                'file_path': _path,
                'tier': 0,
                'reason': 'defect site',
                'content': 'class TaskBloc {}',
                'start_line': 1,
                'end_line': 1,
              },
            ],
            'files': [_path],
            'budget': {'used_lines': 10, 'max_lines': 400},
          }),
          200,
        );
      }

      if (request.url.path.endsWith('/files')) {
        return http.Response(
          jsonEncode({
            'path': _path,
            'content': 'class TaskBloc {}\n',
            'lines': 1,
          }),
          200,
        );
      }

      return http.Response(
        jsonEncode({'detail': 'No patch proposal is available'}),
        502,
      );
    }),
  );
}

Map<String, dynamic> _patchJson() => {
  'status': 'ok',
  'summary': 'fix refresh',
  'reasoning': 'emit loaded',
  'confidence': 0.9,
  'files': [
    {
      'path': _path,
      'language': 'dart',
      'hunks': [
        {'start_line': 1, 'end_line': 1, 'old_text': 'a', 'new_text': 'b'},
      ],
    },
  ],
  'warnings': [],
  'errors': [],
};

Map<String, dynamic> _passedValidationJson() => {
  'status': 'passed',
  'applied': true,
  'validation_passed': true,
  'errors': [],
  'warnings': ['narrow context around TaskBloc'],
  'commands': [
    {
      'name': 'analyze',
      'argv': ['flutter', 'analyze'],
      'exit_code': 0,
      'timed_out': false,
      'stdout': '',
      'stderr': '',
      'duration_ms': 900,
      'passed': true,
    },
  ],
  'runnable': true,
  'unavailable_reason': '',
};

Map<String, dynamic> _approvalJson() => {
  'approved': true,
  'approved_at': '2026-08-30T12:00:00+00:00',
  'commit_sha': 'f0bfc5b317f4984dc2c8d253715e9a30c72c0a5c',
  'analysis_id': 'a1',
};

Map<String, dynamic> _deliveryJson({
  String status = 'succeeded',
  String stage = 'pull_request',
  int? prNumber = 12,
  String? prUrl = 'https://github.com/owner/repo/pull/12',
  List<String> errors = const [],
}) {
  return {
    'status': status,
    'stage': stage,
    'branch': 'patchpilot/issue-1/f0bfc5b317f4',
    'commit_sha': 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
    'base_commit_sha': 'f0bfc5b317f4984dc2c8d253715e9a30c72c0a5c',
    'pr_number': prNumber,
    'pr_url': prUrl,
    'draft': true,
    'errors': errors,
    'warnings': [],
  };
}

ApiClient _artifactApi({
  bool approved = false,
  bool delivered = false,
  void Function()? onApprove,
  void Function()? onDeliver,
  void Function(String id)? onGetAnalysis,
  void Function()? onPostAnalysis,
  Map<String, dynamic>? analysis,
  List<String>? deliverBodies,
  List<Map<String, dynamic>>? deliverQueue,
}) {
  return ApiClient(
    client: MockClient((request) async {
      final path = request.url.path;
      if (request.method == 'POST' && path.endsWith('/analyses')) {
        onPostAnalysis?.call();
        return http.Response(
          jsonEncode({'id': 'a1', 'status': 'queued', 'issue_number': 1}),
          200,
        );
      }
      if (request.method == 'GET' &&
          path.contains('/analyses/') &&
          !path.contains('/patch') &&
          !path.endsWith('/context') &&
          !path.endsWith('/files')) {
        onGetAnalysis?.call(path.split('/').last);
        if (analysis != null) {
          return http.Response(jsonEncode(analysis), 200);
        }
        return http.Response(jsonEncode({'detail': 'missing'}), 404);
      }
      if (path.endsWith('/patch/validate')) {
        return http.Response(jsonEncode(_passedValidationJson()), 200);
      }
      if (path.endsWith('/patch/approve')) {
        if (request.method == 'POST') {
          onApprove?.call();
          return http.Response(jsonEncode(_approvalJson()), 200);
        }
        if (approved) {
          return http.Response(jsonEncode(_approvalJson()), 200);
        }
        return http.Response(
          jsonEncode({'detail': 'This patch has not been approved'}),
          502,
        );
      }
      if (path.endsWith('/patch/deliver')) {
        if (request.method == 'POST') {
          onDeliver?.call();
          deliverBodies?.add(request.body);
          if (deliverQueue != null && deliverQueue.isNotEmpty) {
            return http.Response(jsonEncode(deliverQueue.removeAt(0)), 200);
          }
          return http.Response(jsonEncode(_deliveryJson()), 200);
        }
        if (delivered) {
          return http.Response(jsonEncode(_deliveryJson()), 200);
        }
        return http.Response(
          jsonEncode({'detail': 'No patch delivery is available'}),
          502,
        );
      }
      if (path.endsWith('/patch')) {
        return http.Response(jsonEncode(_patchJson()), 200);
      }
      if (path.endsWith('/context')) {
        return http.Response(
          jsonEncode({
            'issue_id': '1',
            'slices': [],
            'files': [],
            'budget': {'used_lines': 0, 'max_lines': 400},
          }),
          200,
        );
      }
      if (path.endsWith('/files')) {
        return http.Response(
          jsonEncode({
            'path': _path,
            'content': 'class TaskBloc {}\n',
            'lines': 1,
          }),
          200,
        );
      }
      return http.Response(jsonEncode({'detail': 'missing'}), 502);
    }),
  );
}

Future<void> _pumpSession(WidgetTester tester, AnalysisCache cache) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.build(),
      home: RepairSession(
        api: _api(),
        cache: cache,
        repository: _repo,
        issue: _issue,
        onBack: () {},
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> _pumpSessionWithApi(
  WidgetTester tester,
  AnalysisCache cache,
  ApiClient api, {
  GithubRedirect? redirect,
  Repository repository = _repo,
  ValueNotifier<AuthUser?>? session,
  Future<void> Function({
    String? analysisId,
    String? stage,
    String? repairPath,
  })?
  onConnectGithub,
  RepairStage? requestedStage,
  String? resumeAnalysisId,
  String? ref,
  VoidCallback? onBack,
}) async {
  tester.view.physicalSize = const Size(1200, 2400);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);

  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.build(),
      home: RepairSession(
        api: api,
        cache: cache,
        repository: repository,
        issue: _issue,
        ref: ref,
        redirect: redirect,
        session: session,
        onConnectGithub: onConnectGithub,
        requestedStage: requestedStage,
        resumeAnalysisId: resumeAnalysisId,
        onBack: onBack ?? () {},
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('completed diagnosis still shows cause, files, and follow-up', (
    tester,
  ) async {
    final cache = AnalysisCache();
    cache.save(
      AnalysisCache.keyFor(_repo.owner, _repo.repo, _issue.number),
      _completedAnalysis(),
    );

    await _pumpSession(tester, cache);

    expect(
      find.text('TaskBloc never emits TaskLoaded on refresh.'),
      findsOneWidget,
    );
    expect(
      find.text('Emit TaskLoaded after the refresh fetch succeeds.'),
      findsOneWidget,
    );
    expect(
      find.text('The refresh handler stops in TaskLoading.'),
      findsWidgets,
    );
    expect(find.text('View root cause'), findsOneWidget);
    expect(find.byType(RootCauseSection), findsOneWidget);
    expect(find.byType(RelevantFilesSection), findsOneWidget);
    expect(find.byType(ExplanationSection), findsOneWidget);
    expect(find.byType(PatchPanel), findsNothing);
    expect(find.byType(FollowUpPanel), findsNothing);
    expect(find.text('SIGNALS'), findsOneWidget);
    expect(find.text('Continue to Patch'), findsOneWidget);
  });

  testWidgets('repair session keeps one shell across diagnosis to patch', (
    tester,
  ) async {
    final cache = AnalysisCache();
    cache.save(
      AnalysisCache.keyFor(_repo.owner, _repo.repo, _issue.number),
      _completedAnalysis(),
    );

    await _pumpSession(tester, cache);

    expect(find.byType(RepairShell), findsOneWidget);
    expect(find.byType(PatchPanel), findsNothing);

    await tester.tap(find.text('Patch'));
    await tester.pumpAndSettle();

    expect(find.byType(RepairShell), findsOneWidget);
    expect(find.byType(PatchPanel), findsOneWidget);
    expect(find.text('Generate patch'), findsOneWidget);
    expect(find.textContaining('Patching f0bfc5b317f4'), findsOneWidget);
  });

  testWidgets('patch stage shows context and patch; rail has no Context', (
    tester,
  ) async {
    final cache = AnalysisCache();
    cache.save(
      AnalysisCache.keyFor(_repo.owner, _repo.repo, _issue.number),
      _completedAnalysis(),
    );

    await _pumpSession(tester, cache);

    expect(find.text('Diagnosis'), findsOneWidget);
    expect(find.text('Patch'), findsOneWidget);
    expect(find.text('Validation'), findsOneWidget);
    expect(find.text('Review'), findsOneWidget);
    expect(find.text('Pull Request'), findsOneWidget);
    expect(find.widgetWithText(InkWell, 'Context'), findsNothing);

    await tester.tap(find.text('Patch'));
    await tester.pumpAndSettle();

    expect(find.byType(RepairShell), findsOneWidget);
    expect(find.byType(ContextScreen), findsOneWidget);
    expect(find.byType(PatchPanel), findsOneWidget);
    expect(find.text('Generate patch'), findsOneWidget);
    expect(find.text('Build patch →'), findsNothing);
  });

  testWidgets('cache miss starts analysis and polls through to completion', (
    tester,
  ) async {
    var posts = 0;
    var gets = 0;
    final client = ApiClient(
      client: MockClient((request) async {
        final path = request.url.path;
        if (request.method == 'POST' && path.endsWith('/analyses')) {
          posts += 1;
          return http.Response(
            jsonEncode({'id': 'a1', 'status': 'queued', 'issue_number': 1}),
            200,
          );
        }
        if (request.method == 'GET' && path.endsWith('/analyses/a1')) {
          gets += 1;
          if (gets == 1) {
            return http.Response(
              jsonEncode({
                'id': 'a1',
                'status': 'running',
                'stage': 'fetching_issue',
                'issue_number': 1,
              }),
              200,
            );
          }
          return http.Response(
            jsonEncode({
              'id': 'a1',
              'status': 'completed',
              'issue_number': 1,
              'diagnosis': {
                'root_cause': 'TaskBloc never emits TaskLoaded on refresh.',
                'confidence': 0.9,
                'explanation': 'The refresh handler stops in TaskLoading.',
                'suggested_fix':
                    'Emit TaskLoaded after the refresh fetch succeeds.',
                'cited_files': [_path],
              },
            }),
            200,
          );
        }
        return http.Response(
          jsonEncode({'detail': 'No patch proposal is available'}),
          502,
        );
      }),
    );

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.build(),
        home: RepairSession(
          api: client,
          cache: AnalysisCache(),
          repository: _repo,
          issue: _issue,
          onBack: () {},
        ),
      ),
    );

    await tester.pump();
    await tester.pump();

    expect(posts, 1);
    expect(gets, 1);
    expect(find.text('Reading the issue'), findsOneWidget);
    expect(find.text('Continue to Patch'), findsNothing);

    await tester.pump(const Duration(milliseconds: 1200));
    await tester.pump();
    await tester.pump();

    expect(gets, 2);
    expect(find.text('Reading the issue'), findsNothing);
    expect(
      find.text('TaskBloc never emits TaskLoaded on refresh.'),
      findsOneWidget,
    );
    expect(find.text('Analysis complete'), findsWidgets);
    expect(find.text('Continue to Patch'), findsOneWidget);

    await tester.tap(find.text('Patch'));
    await tester.pump();

    expect(find.byType(DiagnosisScreen, skipOffstage: false), findsOneWidget);
    expect(find.byType(RepairShell), findsOneWidget);
  });

  testWidgets('reopening a diagnosed issue shows the cache without posting', (
    tester,
  ) async {
    var posts = 0;
    final cache = AnalysisCache();
    cache.save(
      AnalysisCache.keyFor(_repo.owner, _repo.repo, _issue.number),
      _completedAnalysis(),
    );
    final client = ApiClient(
      client: MockClient((request) async {
        if (request.method == 'POST' &&
            request.url.path.endsWith('/analyses')) {
          posts += 1;
          return http.Response(
            jsonEncode({'id': 'new', 'status': 'queued', 'issue_number': 1}),
            200,
          );
        }
        return http.Response(
          jsonEncode({'detail': 'No patch proposal is available'}),
          502,
        );
      }),
    );

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.build(),
        home: RepairSession(
          api: client,
          cache: cache,
          repository: _repo,
          issue: _issue,
          onBack: () {},
        ),
      ),
    );
    await tester.pump();
    await tester.pump();

    expect(posts, 0);
    expect(
      find.text('TaskBloc never emits TaskLoaded on refresh.'),
      findsOneWidget,
    );
    expect(
      find.text('Showing the result from earlier in this session'),
      findsWidgets,
    );
  });

  testWidgets('file navigation from the diagnosis still opens the viewer', (
    tester,
  ) async {
    final cache = AnalysisCache();
    final analysis = _completedAnalysis();
    cache.save(
      AnalysisCache.keyFor(_repo.owner, _repo.repo, _issue.number),
      analysis,
    );
    cache.saveFile(
      analysis.id,
      const FileSource(path: _path, content: 'class TaskBloc {}\n', lines: 1),
    );

    await _pumpSession(tester, cache);

    await tester.ensureVisible(find.text('View root cause'));
    await tester.tap(find.text('View root cause'));
    await tester.pumpAndSettle();

    expect(find.byType(CodeViewerScreen), findsOneWidget);
    expect(find.textContaining('TaskBloc'), findsWidgets);
  });

  testWidgets('locked stages stay put and explain the prerequisite', (
    tester,
  ) async {
    final cache = AnalysisCache();
    cache.save(
      AnalysisCache.keyFor(_repo.owner, _repo.repo, _issue.number),
      _completedAnalysis(),
    );

    await _pumpSession(tester, cache);

    await tester.tap(find.text('Validation'));
    await tester.pump();

    expect(
      find.text('Generate a patch before opening Validation.'),
      findsOneWidget,
    );
    expect(find.byType(ValidationScreen), findsNothing);
    expect(find.byType(DiagnosisScreen), findsOneWidget);

    await tester.tap(find.text('Review'));
    await tester.pump();

    expect(
      find.text('Validation must pass before opening Review.'),
      findsOneWidget,
    );
    expect(find.byType(ReviewScreen), findsNothing);

    await tester.tap(find.text('Pull Request'));
    await tester.pump();

    expect(
      find.text('Validation must pass before opening the Pull Request.'),
      findsOneWidget,
    );
    expect(find.byType(PullRequestScreen), findsNothing);
  });

  testWidgets('validation stage shows stored Flutter check results', (
    tester,
  ) async {
    final cache = AnalysisCache();
    cache.save(
      AnalysisCache.keyFor(_repo.owner, _repo.repo, _issue.number),
      _completedAnalysis(),
    );

    final api = ApiClient(
      client: MockClient((request) async {
        final path = request.url.path;
        if (path.endsWith('/patch/validate')) {
          return http.Response(
            jsonEncode({
              'status': 'passed',
              'applied': true,
              'validation_passed': true,
              'errors': [],
              'warnings': [],
              'commands': [
                {
                  'name': 'analyze',
                  'argv': ['flutter', 'analyze'],
                  'exit_code': 0,
                  'timed_out': false,
                  'stdout': '',
                  'stderr': '',
                  'duration_ms': 900,
                  'passed': true,
                },
              ],
              'runnable': true,
              'unavailable_reason': '',
            }),
            200,
          );
        }
        if (path.endsWith('/patch')) {
          return http.Response(
            jsonEncode({
              'status': 'ok',
              'summary': 'fix refresh',
              'reasoning': 'emit loaded',
              'confidence': 0.9,
              'files': [
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
              'errors': [],
            }),
            200,
          );
        }
        if (path.endsWith('/context')) {
          return http.Response(
            jsonEncode({
              'issue_id': '1',
              'slices': [],
              'files': [],
              'budget': {'used_lines': 0, 'max_lines': 400},
            }),
            200,
          );
        }
        return http.Response(jsonEncode({'detail': 'missing'}), 502);
      }),
    );

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.build(),
        home: RepairSession(
          api: api,
          cache: cache,
          repository: _repo,
          issue: _issue,
          onBack: () {},
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Validation'));
    await tester.pumpAndSettle();

    expect(find.byType(ValidationScreen), findsOneWidget);
    expect(find.text('Validation passed'), findsOneWidget);
    expect(find.text('Patch applied'), findsOneWidget);
    expect(find.text('flutter analyze'), findsOneWidget);
    expect(find.text('Run validation'), findsNothing);
  });

  testWidgets('review shows real diagnosis, patch, and validation', (
    tester,
  ) async {
    final cache = AnalysisCache();
    cache.save(
      AnalysisCache.keyFor(_repo.owner, _repo.repo, _issue.number),
      _completedAnalysis(),
    );

    await _pumpSessionWithApi(tester, cache, _artifactApi());

    await tester.tap(find.text('Review'));
    await tester.pumpAndSettle();

    expect(find.byType(ReviewScreen), findsOneWidget);
    expect(
      find.text('TaskBloc never emits TaskLoaded on refresh.'),
      findsOneWidget,
    );
    expect(find.textContaining('fix refresh'), findsWidgets);
    expect(find.text(_path), findsWidgets);
    expect(find.text('Validation passed'), findsOneWidget);
    expect(find.text('narrow context around TaskBloc'), findsOneWidget);
    expect(find.text('Approve patch'), findsOneWidget);
  });

  testWidgets('review file tap opens the existing code viewer', (tester) async {
    final cache = AnalysisCache();
    final analysis = _completedAnalysis();
    cache.save(
      AnalysisCache.keyFor(_repo.owner, _repo.repo, _issue.number),
      analysis,
    );
    cache.saveFile(
      analysis.id,
      const FileSource(path: _path, content: 'class TaskBloc {}\n', lines: 1),
    );

    await _pumpSessionWithApi(tester, cache, _artifactApi());

    await tester.tap(find.text('Review'));
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.text(_path));
    await tester.tap(find.text(_path));
    await tester.pumpAndSettle();

    expect(find.byType(CodeViewerScreen), findsOneWidget);
  });

  testWidgets('request changes returns to Patch without a review API', (
    tester,
  ) async {
    final cache = AnalysisCache();
    cache.save(
      AnalysisCache.keyFor(_repo.owner, _repo.repo, _issue.number),
      _completedAnalysis(),
    );

    await _pumpSessionWithApi(tester, cache, _artifactApi());

    await tester.tap(find.text('Review'));
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.text('Request changes'));
    await tester.tap(find.text('Request changes'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'please regenerate');
    await tester.tap(find.widgetWithText(FilledButton, 'Request changes').last);
    await tester.pumpAndSettle();

    expect(find.byType(PatchPanel), findsOneWidget);
    expect(find.byType(ContextScreen), findsOneWidget);
    expect(find.byType(ReviewScreen), findsNothing);
  });

  testWidgets('approve unlocks Pull Request via the existing approve API', (
    tester,
  ) async {
    var approveCalls = 0;
    var deliverCalls = 0;
    final deliverBodies = <String>[];
    final redirect = _TestRedirect();
    final cache = AnalysisCache();
    cache.save(
      AnalysisCache.keyFor(_repo.owner, _repo.repo, _issue.number),
      _completedAnalysis(),
    );

    await _pumpSessionWithApi(
      tester,
      cache,
      _artifactApi(
        onApprove: () => approveCalls += 1,
        onDeliver: () => deliverCalls += 1,
        deliverBodies: deliverBodies,
      ),
      redirect: redirect,
    );

    await tester.tap(find.text('Pull Request'));
    await tester.pump();
    expect(
      find.text('Approve the patch before opening the Pull Request.'),
      findsOneWidget,
    );
    expect(find.byType(PullRequestScreen), findsNothing);

    await tester.tap(find.text('Review'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(
      find.widgetWithText(FilledButton, 'Approve patch'),
    );
    await tester.tap(find.widgetWithText(FilledButton, 'Approve patch'));
    await tester.pumpAndSettle();

    expect(approveCalls, 1);
    expect(find.text('Patch approved'), findsOneWidget);
    expect(find.text('Continue to Pull Request'), findsOneWidget);

    await tester.tap(find.text('Pull Request'));
    await tester.pumpAndSettle();

    expect(find.byType(PullRequestScreen), findsOneWidget);
    expect(find.text('Create pull request'), findsOneWidget);

    await tester.tap(find.text('Create pull request'));
    await tester.pumpAndSettle();

    expect(deliverCalls, 1);
    expect(deliverBodies, hasLength(1));
    final delivered = jsonDecode(deliverBodies.single) as Map<String, dynamic>;
    expect(delivered['title'], 'fix refresh');
    expect(
      delivered['description'],
      contains('TaskBloc never emits TaskLoaded on refresh.'),
    );
    expect(find.text('Pull request #12 created'), findsOneWidget);
    expect(find.text('https://github.com/owner/repo/pull/12'), findsOneWidget);

    await tester.tap(find.text('View pull request'));
    await tester.pump();
    expect(redirect.opened, 'https://github.com/owner/repo/pull/12');
  });

  testWidgets('failed pull request retry uses the same deliver API', (
    tester,
  ) async {
    var deliverCalls = 0;
    final cache = AnalysisCache();
    cache.save(
      AnalysisCache.keyFor(_repo.owner, _repo.repo, _issue.number),
      _completedAnalysis(),
    );

    await _pumpSessionWithApi(
      tester,
      cache,
      _artifactApi(
        onApprove: () {},
        onDeliver: () => deliverCalls += 1,
        deliverQueue: [
          _deliveryJson(
            status: 'failed',
            prNumber: null,
            prUrl: null,
            errors: const ['GitHub permission denied'],
          ),
          _deliveryJson(),
        ],
      ),
    );

    await tester.tap(find.text('Review'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(
      find.widgetWithText(FilledButton, 'Approve patch'),
    );
    await tester.tap(find.widgetWithText(FilledButton, 'Approve patch'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Pull Request'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Create pull request'));
    await tester.pumpAndSettle();

    expect(find.text('Pull request creation failed'), findsOneWidget);
    expect(find.text('GitHub permission denied'), findsOneWidget);
    expect(deliverCalls, 1);

    await tester.tap(find.text('Retry'));
    await tester.pumpAndSettle();

    expect(deliverCalls, 2);
    expect(find.text('Pull request #12 created'), findsOneWidget);
  });

  testWidgets('demo repository PR stage is a completed demo, not a failure', (
    tester,
  ) async {
    var connectCalls = 0;
    var deliverCalls = 0;
    var backCalls = 0;
    final session = ValueNotifier<AuthUser?>(
      const AuthUser(id: 'u1', githubId: 1, githubLogin: 'octocat'),
    );
    addTearDown(session.dispose);
    final cache = AnalysisCache();
    cache.save(
      AnalysisCache.keyFor(_demoRepo.owner, _demoRepo.repo, _issue.number),
      _completedAnalysis(),
    );

    await _pumpSessionWithApi(
      tester,
      cache,
      _artifactApi(
        approved: true,
        onDeliver: () => deliverCalls += 1,
      ),
      repository: _demoRepo,
      session: session,
      onConnectGithub: ({analysisId, stage, repairPath}) async =>
          connectCalls += 1,
      onBack: () => backCalls += 1,
    );

    await tester.tap(find.text('Pull Request'));
    await tester.pumpAndSettle();

    expect(find.text('Repair complete'), findsOneWidget);
    expect(
      find.text(
        'Diagnosis, patch, validation, and review finished. This is a demo repository, so a GitHub pull request cannot be opened here.',
      ),
      findsOneWidget,
    );
    expect(find.text('Passed'), findsWidgets);
    expect(find.text('Approved'), findsWidgets);
    expect(find.text('Return to issues'), findsOneWidget);
    expect(find.text('Create pull request'), findsNothing);
    expect(find.text('Connect GitHub →'), findsNothing);
    expect(find.text('Pull request creation failed'), findsNothing);
    expect(
      find.textContaining('cannot create branches or pull requests'),
      findsNothing,
    );

    await tester.tap(find.text('Return to issues'));
    await tester.pump();

    expect(backCalls, 1);
    expect(deliverCalls, 0);
    expect(connectCalls, 0);
  });

  testWidgets('anonymous demo PR stage asks to connect GitHub, not create a PR', (
    tester,
  ) async {
    var connectCalls = 0;
    var deliverCalls = 0;
    final cache = AnalysisCache();
    cache.save(
      AnalysisCache.keyFor(_demoRepo.owner, _demoRepo.repo, _issue.number),
      _completedAnalysis(),
    );

    await _pumpSessionWithApi(
      tester,
      cache,
      _artifactApi(approved: true, onDeliver: () => deliverCalls += 1),
      repository: _demoRepo,
      onConnectGithub: ({analysisId, stage, repairPath}) async =>
          connectCalls += 1,
    );

    await tester.tap(find.text('Pull Request'));
    await tester.pumpAndSettle();

    expect(find.text('Connect GitHub →'), findsOneWidget);
    expect(find.text('Repair complete'), findsNothing);
    expect(find.text('Create pull request'), findsNothing);
    expect(find.text('Pull request creation failed'), findsNothing);
    expect(connectCalls, 0);
    expect(deliverCalls, 0);
  });

  testWidgets(
    'Pull Request Connect GitHub supplies the RepairSession repairPath',
    (tester) async {
      String? capturedId;
      String? capturedStage;
      String? capturedPath;
      final cache = AnalysisCache();
      cache.save(
        AnalysisCache.keyFor(
          _demoRepo.owner,
          _demoRepo.repo,
          _issue.number,
          ref: 'deadbeef',
        ),
        _completedAnalysis(),
      );

      await _pumpSessionWithApi(
        tester,
        cache,
        _artifactApi(approved: true),
        repository: _demoRepo,
        ref: 'deadbeef',
        onConnectGithub: ({analysisId, stage, repairPath}) async {
          capturedId = analysisId;
          capturedStage = stage;
          capturedPath = repairPath;
        },
      );

      await tester.tap(find.text('Pull Request'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Connect GitHub →'));
      await tester.pump();

      expect(capturedId, 'a1');
      expect(capturedStage, 'pull-request');
      expect(
        capturedPath,
        AppRoutes.repair(
          owner: _demoRepo.owner,
          repo: _demoRepo.repo,
          number: _issue.number,
          stage: RepairStage.pullRequest,
          ref: 'deadbeef',
        ),
      );
    },
  );

  testWidgets(
    'Pull Request Connect GitHub shows a spinner while connecting',
    (tester) async {
      final gate = Completer<void>();
      final cache = AnalysisCache();
      cache.save(
        AnalysisCache.keyFor(
          _demoRepo.owner,
          _demoRepo.repo,
          _issue.number,
          ref: 'deadbeef',
        ),
        _completedAnalysis(),
      );

      await _pumpSessionWithApi(
        tester,
        cache,
        _artifactApi(approved: true),
        repository: _demoRepo,
        ref: 'deadbeef',
        onConnectGithub: ({analysisId, stage, repairPath}) => gate.future,
      );

      await tester.tap(find.text('Pull Request'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Connect GitHub →'));
      await tester.pump();

      expect(
        find.descendant(
          of: find.byType(PullRequestScreen),
          matching: find.byType(AppSpinner),
        ),
        findsOneWidget,
      );
      expect(find.text('Connect GitHub →'), findsNothing);

      gate.complete();
      await tester.pump();

      expect(find.text('Connect GitHub →'), findsOneWidget);
    },
  );

  testWidgets('cache-first diagnosis is unchanged when there is no resume', (
    tester,
  ) async {
    var posts = 0;
    final got = <String>[];
    final cache = AnalysisCache();
    cache.save(
      AnalysisCache.keyFor(_repo.owner, _repo.repo, _issue.number),
      _completedAnalysis(),
    );

    await _pumpSessionWithApi(
      tester,
      cache,
      _artifactApi(
        analysis: _completedAnalysisJson(),
        onGetAnalysis: got.add,
        onPostAnalysis: () => posts += 1,
      ),
    );

    expect(
      find.text('TaskBloc never emits TaskLoaded on refresh.'),
      findsOneWidget,
    );
    expect(find.text('Stale cached root cause.'), findsNothing);
    expect(posts, 0);
    expect(got, isEmpty);
  });

  testWidgets('resumeAnalysisId beats a stale local cache and GETs once', (
    tester,
  ) async {
    var posts = 0;
    final got = <String>[];
    final cache = AnalysisCache();
    cache.save(
      AnalysisCache.keyFor(_repo.owner, _repo.repo, _issue.number),
      _staleAnalysis(),
    );

    await _pumpSessionWithApi(
      tester,
      cache,
      _artifactApi(
        analysis: _completedAnalysisJson(),
        onGetAnalysis: got.add,
        onPostAnalysis: () => posts += 1,
      ),
      resumeAnalysisId: 'a1',
    );

    expect(
      find.text('TaskBloc never emits TaskLoaded on refresh.'),
      findsOneWidget,
    );
    expect(find.text('Stale cached root cause.'), findsNothing);
    expect(posts, 0);
    expect(got, ['a1']);
  });

  testWidgets('resumed Pull Request stage stays on Pull Request', (
    tester,
  ) async {
    var posts = 0;
    final got = <String>[];
    final cache = AnalysisCache();
    cache.save(
      AnalysisCache.keyFor(_repo.owner, _repo.repo, _issue.number),
      _staleAnalysis(),
    );

    await _pumpSessionWithApi(
      tester,
      cache,
      _artifactApi(
        approved: true,
        analysis: _completedAnalysisJson(),
        onGetAnalysis: got.add,
        onPostAnalysis: () => posts += 1,
      ),
      resumeAnalysisId: 'a1',
      requestedStage: RepairStage.pullRequest,
    );

    expect(find.byType(PullRequestScreen), findsOneWidget);
    expect(find.text('Create pull request'), findsOneWidget);
    expect(
      find.text('TaskBloc never emits TaskLoaded on refresh.'),
      findsNothing,
    );
    expect(find.text('Stale cached root cause.'), findsNothing);
    expect(posts, 0);
    expect(got, ['a1']);
  });

  testWidgets('invalid resume analysisId falls back to a new diagnosis', (
    tester,
  ) async {
    var posts = 0;
    var gets = 0;
    final cache = AnalysisCache();
    cache.save(
      AnalysisCache.keyFor(_repo.owner, _repo.repo, _issue.number),
      _staleAnalysis(),
    );
    final client = ApiClient(
      client: MockClient((request) async {
        final path = request.url.path;
        if (request.method == 'GET' && path.endsWith('/analyses/missing')) {
          gets += 1;
          return http.Response(
            jsonEncode({'detail': 'No analysis with id missing'}),
            404,
          );
        }
        if (request.method == 'POST' && path.endsWith('/analyses')) {
          posts += 1;
          return http.Response(jsonEncode(_completedAnalysisJson()), 200);
        }
        return http.Response(
          jsonEncode({'detail': 'No patch proposal is available'}),
          502,
        );
      }),
    );

    await _pumpSessionWithApi(
      tester,
      cache,
      client,
      resumeAnalysisId: 'missing',
    );

    expect(
      find.text('TaskBloc never emits TaskLoaded on refresh.'),
      findsOneWidget,
    );
    expect(find.text('Stale cached root cause.'), findsNothing);
    expect(gets, 1);
    expect(posts, 1);
  });
}

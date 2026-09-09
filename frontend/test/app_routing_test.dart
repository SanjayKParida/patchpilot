import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:patchpilot_web/app/app.dart';
import 'package:patchpilot_web/app/app_routes.dart';
import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/features/repair/shell/repair_session.dart';
import 'package:patchpilot_web/features/repair/shell/repair_workflow.dart';
import 'package:patchpilot_web/features/repositories/screens/issues_screen.dart';
import 'package:patchpilot_web/models/models.dart';
import 'package:patchpilot_web/services/analysis_cache.dart';
import 'package:patchpilot_web/services/api_client.dart';

http.Response _json(Object body, [int status = 200]) {
  return http.Response(
    jsonEncode(body),
    status,
    headers: const {'content-type': 'application/json; charset=utf-8'},
  );
}

const _demo = {
  'owner': 'SanjayKParida',
  'repo': 'patchpilot-diagnosis-demo',
  'full_name': 'SanjayKParida/patchpilot-diagnosis-demo',
  'description': 'Try PatchPilot on prepared issues',
  'demo': true,
};

const _repo = Repository(owner: 'owner', repo: 'repo', fullName: 'owner/repo');

const _issue = Issue(number: 1, title: 'Refresh spinner never stops');

const _completedAnalysisJson = {
  'id': 'a1',
  'status': 'completed',
  'issue_number': 1,
  'diagnosis': {
    'root_cause': 'TaskBloc never emits TaskLoaded on refresh.',
    'confidence': 0.9,
    'explanation': 'The refresh handler stops in TaskLoading.',
    'suggested_fix': 'Emit TaskLoaded after the refresh fetch succeeds.',
    'cited_files': ['lib/bloc/task_bloc.dart'],
  },
};

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
      citedFiles: ['lib/bloc/task_bloc.dart'],
    ),
  );
}

ApiClient _demoApi() {
  return ApiClient(
    client: MockClient((request) async {
      final path = request.url.path;
      if (path.endsWith('/auth/me')) {
        return _json({'authenticated': false, 'user': null});
      }
      if (path.endsWith('/repositories/demo')) {
        return _json(_demo);
      }
      if (path.endsWith('/issues')) {
        return _json([
          {
            'number': 1,
            'title': 'Refresh spinner never stops',
            'body': 'Spinner stays.',
            'state': 'open',
            'comments': 0,
          },
        ]);
      }
      if (path.endsWith('/snapshot')) {
        return _json({
          'commit_sha': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
          'status': 'ready',
          'file_count': 12,
        });
      }
      if (path.endsWith('/analyses') && request.method == 'POST') {
        return _json(_completedAnalysisJson);
      }
      if (path.contains('/analyses/')) {
        return _json(_completedAnalysisJson);
      }
      return _json({'detail': 'nope'}, 404);
    }),
  );
}

void main() {
  test('AppRoutes maps stages to path segments', () {
    expect(AppRoutes.issues('acme', 'widgets'), '/r/acme/widgets');
    expect(
      AppRoutes.repair(owner: 'acme', repo: 'widgets', number: 7),
      '/r/acme/widgets/issues/7/diagnosis',
    );
    expect(
      AppRoutes.repair(
        owner: 'acme',
        repo: 'widgets',
        number: 7,
        stage: RepairStage.patch,
        ref: 'main',
      ),
      '/r/acme/widgets/issues/7/patch?ref=main',
    );
    expect(AppRoutes.stageFrom('pull-request'), RepairStage.pullRequest);
    expect(AppRoutes.stageFrom('context'), RepairStage.patch);
    expect(AppRoutes.stageFrom('nope'), RepairStage.diagnosis);
  });

  testWidgets('Dashboard then Issues then Repair create go-router locations', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1200, 2400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(PatchPilotApp(api: _demoApi()));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    await tester.pump(const Duration(milliseconds: 50));

    expect(
      find.text('SanjayKParida/patchpilot-diagnosis-demo'),
      findsOneWidget,
    );

    await tester.tap(find.text('SanjayKParida/patchpilot-diagnosis-demo'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));

    expect(find.byType(IssuesScreen), findsOneWidget);
    var location = GoRouter.of(tester.element(find.byType(IssuesScreen)));
    expect(
      location.state.uri.path,
      '/r/SanjayKParida/patchpilot-diagnosis-demo',
    );

    await tester.tap(find.text('Refresh spinner never stops'));
    await tester.pump();
    await tester.pump();
    await tester.pump();

    expect(find.byType(RepairSession), findsOneWidget);
    final session = tester.state(find.byType(RepairSession));
    location = GoRouter.of(tester.element(find.byType(RepairSession)));
    expect(
      location.state.uri.path,
      '/r/SanjayKParida/patchpilot-diagnosis-demo/issues/1/diagnosis',
    );
    expect(
      find.text('TaskBloc never emits TaskLoaded on refresh.'),
      findsOneWidget,
    );

    await tester.tap(find.text('Patch'));
    await tester.pump();
    await tester.pump();

    location = GoRouter.of(tester.element(find.byType(RepairSession)));
    expect(
      location.state.uri.path,
      '/r/SanjayKParida/patchpilot-diagnosis-demo/issues/1/patch',
    );
    expect(tester.state(find.byType(RepairSession)), same(session));

    if (location.canPop()) {
      location.pop();
    } else {
      location.go(
        '/r/SanjayKParida/patchpilot-diagnosis-demo/issues/1/diagnosis',
      );
    }
    await tester.pump();
    await tester.pump();

    expect(
      location.state.uri.path,
      '/r/SanjayKParida/patchpilot-diagnosis-demo/issues/1/diagnosis',
    );
    expect(tester.state(find.byType(RepairSession)), same(session));
    expect(
      find.text('TaskBloc never emits TaskLoaded on refresh.'),
      findsOneWidget,
    );

    location.go('/r/SanjayKParida/patchpilot-diagnosis-demo/issues/1/review');
    await tester.pump();
    await tester.pump();
    await tester.pump();

    expect(find.byType(RepairSession), findsOneWidget);
    location = GoRouter.of(tester.element(find.byType(RepairSession)));
    expect(
      location.state.uri.path,
      '/r/SanjayKParida/patchpilot-diagnosis-demo/issues/1/patch',
    );
    expect(
      find.text('Validation must pass before opening Review.'),
      findsOneWidget,
    );
  });

  testWidgets('accepted Patch stage reports a committed go, not replace', (
    tester,
  ) async {
    final cache = AnalysisCache();
    cache.save(
      AnalysisCache.keyFor(_repo.owner, _repo.repo, _issue.number),
      _completedAnalysis(),
    );
    final committed = <RepairStage>[];
    final normalized = <RepairStage>[];

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.build(),
        home: RepairSession(
          api: ApiClient(
            client: MockClient(
              (request) async => http.Response('{"detail":"none"}', 502),
            ),
          ),
          cache: cache,
          repository: _repo,
          issue: _issue,
          onBack: () {},
          onStageCommitted: committed.add,
          onStageNormalized: normalized.add,
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Patch'));
    await tester.pumpAndSettle();

    expect(committed, [RepairStage.patch]);
    expect(normalized, isEmpty);
  });

  testWidgets('locked requested Review normalizes without committing go', (
    tester,
  ) async {
    final cache = AnalysisCache();
    cache.save(
      AnalysisCache.keyFor(_repo.owner, _repo.repo, _issue.number),
      _completedAnalysis(),
    );
    final committed = <RepairStage>[];
    final normalized = <RepairStage>[];

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.build(),
        home: RepairSession(
          api: ApiClient(
            client: MockClient(
              (request) async => http.Response('{"detail":"none"}', 502),
            ),
          ),
          cache: cache,
          repository: _repo,
          issue: _issue,
          onBack: () {},
          requestedStage: RepairStage.review,
          onStageCommitted: committed.add,
          onStageNormalized: normalized.add,
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(committed, isEmpty);
    expect(normalized, [RepairStage.patch]);
    expect(
      find.text('Validation must pass before opening Review.'),
      findsOneWidget,
    );
  });
}

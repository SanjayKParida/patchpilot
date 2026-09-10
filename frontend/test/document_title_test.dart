import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:patchpilot_web/app/app.dart';
import 'package:patchpilot_web/app/app_routes.dart';
import 'package:patchpilot_web/features/dashboard/screens/dashboard_screen.dart';
import 'package:patchpilot_web/features/repair/shell/repair_session.dart';
import 'package:patchpilot_web/features/repair/shell/repair_workflow.dart';
import 'package:patchpilot_web/features/repositories/screens/issues_screen.dart';
import 'package:patchpilot_web/models/models.dart';
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

String _title(WidgetTester tester) {
  return tester.widget<Title>(find.byType(Title)).title;
}

Future<void> _pumpApp(WidgetTester tester) async {
  tester.view.physicalSize = const Size(1200, 2400);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);

  await tester.pumpWidget(PatchPilotApp(api: _demoApi()));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 50));
  await tester.pump(const Duration(milliseconds: 50));
}

GoRouter _router(WidgetTester tester) {
  return GoRouter.of(tester.element(find.byType(DashboardScreen)));
}

void main() {
  test('documentTitle maps dashboard, issues, and each repair stage', () {
    expect(AppRoutes.documentTitle(Uri.parse('/')), 'PatchPilot');
    expect(AppRoutes.documentTitle(Uri.parse('')), 'PatchPilot');
    expect(
      AppRoutes.documentTitle(Uri.parse('/r/acme/widgets')),
      'Issues · PatchPilot',
    );
    expect(
      AppRoutes.documentTitle(
        Uri.parse(AppRoutes.repair(owner: 'acme', repo: 'widgets', number: 3)),
      ),
      'Diagnosis · PatchPilot',
    );
    expect(
      AppRoutes.documentTitle(
        Uri.parse(
          AppRoutes.repair(
            owner: 'acme',
            repo: 'widgets',
            number: 3,
            stage: RepairStage.patch,
          ),
        ),
      ),
      'Patch · PatchPilot',
    );
    expect(
      AppRoutes.documentTitle(Uri.parse('/r/acme/widgets/issues/3/context')),
      'Patch · PatchPilot',
    );
    expect(
      AppRoutes.documentTitle(
        Uri.parse(
          AppRoutes.repair(
            owner: 'acme',
            repo: 'widgets',
            number: 3,
            stage: RepairStage.validation,
          ),
        ),
      ),
      'Validation · PatchPilot',
    );
    expect(
      AppRoutes.documentTitle(
        Uri.parse(
          AppRoutes.repair(
            owner: 'acme',
            repo: 'widgets',
            number: 3,
            stage: RepairStage.review,
          ),
        ),
      ),
      'Review · PatchPilot',
    );
    expect(
      AppRoutes.documentTitle(
        Uri.parse(
          AppRoutes.repair(
            owner: 'acme',
            repo: 'widgets',
            number: 3,
            stage: RepairStage.pullRequest,
            ref: 'abc',
          ),
        ),
      ),
      'Pull Request · PatchPilot',
    );
    expect(
      AppRoutes.documentTitle(
        Uri.parse(
          '/r/acme/widgets/issues/3/pull-request?analysis_id=a1&connected=1',
        ),
      ),
      'Pull Request · PatchPilot',
    );
  });

  test('documentTitle falls back to PatchPilot for unknown paths', () {
    expect(AppRoutes.documentTitle(Uri.parse('/not-a-route')), 'PatchPilot');
    expect(AppRoutes.documentTitle(Uri.parse('/r/only-owner')), 'PatchPilot');
    expect(
      AppRoutes.documentTitle(Uri.parse('/r/acme/widgets/issues/3/nope')),
      'PatchPilot',
    );
    expect(AppRoutes.documentTitle(null), 'PatchPilot');
  });

  testWidgets('dashboard uses the PatchPilot tab title', (tester) async {
    await _pumpApp(tester);
    expect(find.byType(DashboardScreen), findsOneWidget);
    expect(_title(tester), 'PatchPilot');
  });

  testWidgets('issues and repair navigation update the tab title', (
    tester,
  ) async {
    await _pumpApp(tester);

    await tester.tap(find.text('SanjayKParida/patchpilot-diagnosis-demo'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));

    expect(find.byType(IssuesScreen), findsOneWidget);
    expect(_title(tester), 'Issues · PatchPilot');

    await tester.tap(find.text('Refresh spinner never stops'));
    await tester.pump();
    await tester.pump();
    await tester.pump();

    expect(find.byType(RepairSession), findsOneWidget);
    expect(_title(tester), 'Diagnosis · PatchPilot');

    await tester.tap(find.text('Patch'));
    await tester.pump();
    await tester.pump();

    expect(_title(tester), 'Patch · PatchPilot');
  });

  testWidgets('each repair stage path sets the matching tab title', (
    tester,
  ) async {
    await _pumpApp(tester);
    final router = _router(tester);

    const stages = <RepairStage, String>{
      RepairStage.diagnosis: 'Diagnosis · PatchPilot',
      RepairStage.patch: 'Patch · PatchPilot',
      RepairStage.validation: 'Validation · PatchPilot',
      RepairStage.review: 'Review · PatchPilot',
      RepairStage.pullRequest: 'Pull Request · PatchPilot',
    };

    for (final entry in stages.entries) {
      router.go(
        AppRoutes.repair(
          owner: 'SanjayKParida',
          repo: 'patchpilot-diagnosis-demo',
          number: 1,
          stage: entry.key,
        ),
      );
      await tester.pump();
      expect(_title(tester), entry.value);
    }
  });

  testWidgets('unknown route falls back to PatchPilot', (tester) async {
    await _pumpApp(tester);
    _router(tester).go('/definitely-not-a-route');
    await tester.pump();
    expect(_title(tester), 'PatchPilot');
  });
}

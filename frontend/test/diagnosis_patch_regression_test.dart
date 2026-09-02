import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:patchpilot_web/models/models.dart';
import 'package:patchpilot_web/features/repair/code_viewer/screens/code_viewer_screen.dart';
import 'package:patchpilot_web/features/repair/diagnosis/screens/diagnosis_screen.dart';
import 'package:patchpilot_web/services/analysis_cache.dart';
import 'package:patchpilot_web/services/api_client.dart';
import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/features/repair/diagnosis/widgets/explanation_section.dart';
import 'package:patchpilot_web/features/repair/diagnosis/widgets/follow_up.dart';
import 'package:patchpilot_web/features/repair/diagnosis/widgets/relevant_files_section.dart';
import 'package:patchpilot_web/features/repair/diagnosis/widgets/root_cause_section.dart';
import 'package:patchpilot_web/features/repair/patch/widgets/patch_panel.dart';

const _path = 'lib/bloc/task_bloc.dart';

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

ApiClient _api() {
  return ApiClient(
    client: MockClient((request) async {
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

void main() {
  testWidgets('completed diagnosis still shows cause, files, and follow-up', (
    tester,
  ) async {
    final cache = AnalysisCache();
    const repo = Repository(
      owner: 'owner',
      repo: 'repo',
      fullName: 'owner/repo',
    );
    const issue = Issue(
      number: 1,
      title: 'Refresh spinner never stops',
      body: 'Pull to refresh stays on TaskLoading.',
    );
    cache.save(
      AnalysisCache.keyFor(repo.owner, repo.repo, issue.number),
      _completedAnalysis(),
    );

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.build(),
        home: DiagnosisScreen(
          api: _api(),
          cache: cache,
          repository: repo,
          issue: issue,
          onBack: () {},
        ),
      ),
    );
    await tester.pumpAndSettle();

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
    expect(find.byType(PatchPanel), findsOneWidget);
    expect(find.byType(FollowUpPanel), findsOneWidget);
    expect(find.text('Generate patch'), findsOneWidget);
    expect(find.textContaining('Patching f0bfc5b317f4'), findsOneWidget);
    expect(find.text('SIGNALS'), findsOneWidget);
  });

  testWidgets('file navigation from the diagnosis still opens the viewer', (
    tester,
  ) async {
    final cache = AnalysisCache();
    const repo = Repository(
      owner: 'owner',
      repo: 'repo',
      fullName: 'owner/repo',
    );
    const issue = Issue(number: 1, title: 'Refresh spinner never stops');
    final analysis = _completedAnalysis();
    cache.save(
      AnalysisCache.keyFor(repo.owner, repo.repo, issue.number),
      analysis,
    );
    cache.saveFile(
      analysis.id,
      const FileSource(path: _path, content: 'class TaskBloc {}\n', lines: 1),
    );

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.build(),
        home: DiagnosisScreen(
          api: _api(),
          cache: cache,
          repository: repo,
          issue: issue,
          onBack: () {},
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.text('View root cause'));
    await tester.tap(find.text('View root cause'));
    await tester.pumpAndSettle();

    expect(find.byType(CodeViewerScreen), findsOneWidget);
    expect(find.textContaining('TaskBloc'), findsWidgets);
  });
}

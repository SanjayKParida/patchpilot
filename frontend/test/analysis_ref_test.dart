import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:patchpilot_web/models/models.dart';
import 'package:patchpilot_web/features/repair/diagnosis/screens/diagnosis_screen.dart';
import 'package:patchpilot_web/services/analysis_cache.dart';
import 'package:patchpilot_web/services/api_client.dart';
import 'package:patchpilot_web/core/theme/app_theme.dart';

void main() {
  test('parses requested ref and resolved commit from the API', () {
    final analysis = Analysis.fromJson(const {
      'id': 'a1',
      'status': 'completed',
      'issue_number': 3,
      'ref': 'f0bfc5b',
      'commit_sha': 'f0bfc5b317f4984dc2c8d253715e9a30c72c0a5c',
    });

    expect(analysis.ref, 'f0bfc5b');
    expect(analysis.commitSha, 'f0bfc5b317f4984dc2c8d253715e9a30c72c0a5c');
  });

  testWidgets('diagnosis header shows the analyzed commit', (tester) async {
    const sha = 'f0bfc5b317f4984dc2c8d253715e9a30c72c0a5c';
    final cache = AnalysisCache();
    const repo = Repository(
      owner: 'owner',
      repo: 'repo',
      fullName: 'owner/repo',
    );
    const issue = Issue(number: 3, title: 'Active filter');
    cache.save(
      AnalysisCache.keyFor(repo.owner, repo.repo, issue.number, ref: sha),
      Analysis(
        id: 'a1',
        status: AnalysisStatus.completed,
        issueNumber: 3,
        commitSha: sha,
        ref: sha,
        diagnosis: const Diagnosis(
          rootCause: 'Active filter uses task.isCompleted.',
          confidence: 0.9,
          explanation: 'Predicate is inverted.',
          suggestedFix: 'Use !task.isCompleted.',
          citedFiles: ['lib/domain/usecases/get_filtered_tasks.dart'],
        ),
      ),
    );

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.build(),
        home: DiagnosisScreen(
          api: ApiClient(
            client: MockClient(
              (request) async => http.Response('{"detail":"none"}', 502),
            ),
          ),
          cache: cache,
          repository: repo,
          issue: issue,
          ref: sha,
          onBack: () {},
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('Analyzed at f0bfc5b317f4'), findsOneWidget);
    expect(find.textContaining('Patching f0bfc5b317f4'), findsOneWidget);
    expect(find.text('Generate patch'), findsOneWidget);
    expect(find.text('Active filter uses task.isCompleted.'), findsOneWidget);
  });
}

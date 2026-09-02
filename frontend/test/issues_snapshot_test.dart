import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:patchpilot_web/models/models.dart';
import 'package:patchpilot_web/features/repositories/screens/issues_screen.dart';
import 'package:patchpilot_web/services/api_client.dart';

http.Response _json(Object body, [int status = 200]) {
  return http.Response(
    jsonEncode(body),
    status,
    headers: const {'content-type': 'application/json; charset=utf-8'},
  );
}

const _repo = Repository(
  owner: 'octocat',
  repo: 'hello-world',
  fullName: 'octocat/hello-world',
  description: 'demo repo',
);

void main() {
  test('prepareRepositorySnapshot waits 180s like other long jobs', () {
    expect(ApiClient.snapshotPrepareTimeout, const Duration(seconds: 180));
  });

  test('prepareRepositorySnapshot returns a ready snapshot', () async {
    var posts = 0;
    final api = ApiClient(
      client: MockClient((request) async {
        if (request.method == 'POST' &&
            request.url.path.endsWith('/snapshot')) {
          posts += 1;
          return _json({
            'commit_sha': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
            'status': 'ready',
            'file_count': 12,
          });
        }
        fail('unexpected ${request.method} ${request.url}');
      }),
    );

    final snapshot = await api.prepareRepositorySnapshot(
      'octocat',
      'hello-world',
    );

    expect(snapshot.isReady, isTrue);
    expect(snapshot.fileCount, 12);
    expect(posts, 1);
  });

  test('409 running then GET ready does not start another download', () async {
    var posts = 0;
    var gets = 0;
    final api = ApiClient(
      client: MockClient((request) async {
        if (request.method == 'POST' &&
            request.url.path.endsWith('/snapshot')) {
          posts += 1;
          return _json({
            'detail': 'Repository snapshot preparation is already running',
          }, 409);
        }
        if (request.method == 'GET' && request.url.path.endsWith('/snapshot')) {
          gets += 1;
          if (gets < 2) {
            return _json({
              'commit_sha': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
              'status': 'running',
              'file_count': 0,
            });
          }
          return _json({
            'commit_sha': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
            'status': 'ready',
            'file_count': 4,
          });
        }
        fail('unexpected ${request.method} ${request.url}');
      }),
    );

    final snapshot = await api.prepareRepositorySnapshot(
      'octocat',
      'hello-world',
      timeout: const Duration(seconds: 2),
      pollInterval: const Duration(milliseconds: 1),
    );

    expect(snapshot.isReady, isTrue);
    expect(snapshot.fileCount, 4);
    expect(posts, 1);
    expect(gets, 2);
  });

  testWidgets('opening issues prepares a snapshot in parallel', (tester) async {
    var issueCalls = 0;
    var snapshotCalls = 0;
    final api = ApiClient(
      client: MockClient((request) async {
        if (request.url.path.endsWith('/issues')) {
          issueCalls += 1;
          return _json([
            {
              'number': 1,
              'title': 'Spinner stuck',
              'body': '',
              'state': 'open',
            },
          ]);
        }
        if (request.method == 'POST' &&
            request.url.path.endsWith('/snapshot')) {
          snapshotCalls += 1;
          return _json({
            'commit_sha': 'f0bfc5b317f4984dc2c8d253715e9a30c72c0a5c',
            'status': 'ready',
            'file_count': 18,
          });
        }
        return _json({'detail': 'nope'}, 404);
      }),
    );

    await tester.pumpWidget(
      MaterialApp(
        home: IssuesScreen(
          api: api,
          repository: _repo,
          onIssueSelected: (_, {String? ref}) {},
          onBack: () {},
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(issueCalls, 1);
    expect(snapshotCalls, 1);
    expect(find.text('Spinner stuck'), findsOneWidget);
    expect(find.textContaining('Repository ready at f0bfc5b'), findsOneWidget);
    expect(find.textContaining('18 files'), findsOneWidget);
  });

  testWidgets('snapshot failure does not hide the issue list', (tester) async {
    final api = ApiClient(
      client: MockClient((request) async {
        if (request.url.path.endsWith('/issues')) {
          return _json([
            {'number': 2, 'title': 'Empty state', 'body': '', 'state': 'open'},
          ]);
        }
        if (request.url.path.endsWith('/snapshot')) {
          return _json({'detail': 'GitHub timed out'}, 502);
        }
        return _json({'detail': 'nope'}, 404);
      }),
    );

    await tester.pumpWidget(
      MaterialApp(
        home: IssuesScreen(
          api: api,
          repository: _repo,
          onIssueSelected: (_, {String? ref}) {},
          onBack: () {},
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Empty state'), findsOneWidget);
    expect(
      find.textContaining('Could not prepare the repository: GitHub timed out'),
      findsOneWidget,
    );
  });

  testWidgets('shows download progress while the snapshot is preparing', (
    tester,
  ) async {
    final gate = Completer<http.Response>();
    final api = ApiClient(
      client: MockClient((request) async {
        if (request.url.path.endsWith('/issues')) {
          return _json([
            {
              'number': 1,
              'title': 'Spinner stuck',
              'body': '',
              'state': 'open',
            },
          ]);
        }
        if (request.method == 'GET' && request.url.path.endsWith('/snapshot')) {
          return _json({
            'commit_sha': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
            'status': 'running',
            'file_count': 0,
            'progress_percent': 37,
            'files_downloaded': 37,
            'files_total': 100,
          });
        }
        if (request.method == 'POST' &&
            request.url.path.endsWith('/snapshot')) {
          return gate.future;
        }
        return _json({'detail': 'nope'}, 404);
      }),
    );

    await tester.pumpWidget(
      MaterialApp(
        home: IssuesScreen(
          api: api,
          repository: _repo,
          onIssueSelected: (_, {String? ref}) {},
          onBack: () {},
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    expect(find.textContaining('Preparing repository… 37%'), findsOneWidget);
    expect(find.byType(LinearProgressIndicator), findsOneWidget);

    final analyze = tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, 'Analyze'),
    );
    expect(analyze.onPressed, isNull);

    gate.complete(
      _json({
        'commit_sha': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        'status': 'ready',
        'file_count': 100,
        'progress_percent': 100,
        'files_downloaded': 100,
        'files_total': 100,
      }),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('Repository ready at aaaaaaa'), findsOneWidget);
    final readyAnalyze = tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, 'Analyze'),
    );
    expect(readyAnalyze.onPressed, isNotNull);
  });
}

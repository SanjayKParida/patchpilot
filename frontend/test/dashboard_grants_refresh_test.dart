import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/features/dashboard/screens/dashboard_screen.dart';
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

const _cached = [
  {
    'owner': 'octocat',
    'repo': 'circle_marketplace',
    'full_name': 'octocat/circle_marketplace',
    'private': false,
    'can_read': true,
    'can_write': true,
    'access': 'write',
  },
];

const _refreshed = [
  ..._cached,
  {
    'owner': 'octocat',
    'repo': 'project-aether',
    'full_name': 'octocat/project-aether',
    'private': true,
    'can_read': true,
    'can_write': false,
    'access': 'read',
  },
];

const _user = AuthUser(
  id: 'u1',
  githubId: 4242,
  githubLogin: 'octocat',
);

ApiClient _client(Future<http.Response> Function(http.Request) handler) {
  return ApiClient(client: MockClient(handler));
}

Future<void> _pumpDashboard(
  WidgetTester tester, {
  required ApiClient api,
  bool refreshGrantsOnStart = false,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.build(),
      home: DashboardScreen(
        api: api,
        session: ValueNotifier<AuthUser?>(_user),
        refreshGrantsOnStart: refreshGrantsOnStart,
        onConnectGithub: () async {},
        onManageGithub: () async {},
        onLogout: () async {},
        onRepositorySelected: (_) {},
      ),
    ),
  );
}

void main() {
  testWidgets('cached repositories display immediately', (tester) async {
    final refresh = Completer<http.Response>();
    var posts = 0;
    final api = _client((request) async {
      if (request.url.path.endsWith('/repositories/demo')) {
        return _json(_demo);
      }
      if (request.method == 'POST' &&
          request.url.path.endsWith('/authorized/refresh')) {
        posts += 1;
        return refresh.future;
      }
      if (request.url.path.endsWith('/repositories/authorized')) {
        return _json(_cached);
      }
      return _json({'detail': 'nope'}, 404);
    });

    await _pumpDashboard(tester, api: api);
    await tester.pump();
    await tester.pump();

    expect(find.text('octocat/circle_marketplace'), findsOneWidget);
    expect(find.text('octocat/project-aether'), findsNothing);
    expect(find.text('1 connected'), findsOneWidget);
    expect(posts, 1);

    refresh.complete(_json(_refreshed));
    await tester.pump();
    await tester.pump();

    expect(find.text('octocat/project-aether'), findsOneWidget);
    expect(find.text('2 connected'), findsOneWidget);
  });

  testWidgets('authenticated Dashboard triggers one background refresh', (
    tester,
  ) async {
    var gets = 0;
    var posts = 0;
    final api = _client((request) async {
      if (request.url.path.endsWith('/repositories/demo')) {
        return _json(_demo);
      }
      if (request.method == 'POST' &&
          request.url.path.endsWith('/authorized/refresh')) {
        posts += 1;
        return _json(_refreshed);
      }
      if (request.url.path.endsWith('/repositories/authorized')) {
        gets += 1;
        return _json(_cached);
      }
      return _json({'detail': 'nope'}, 404);
    });

    await _pumpDashboard(tester, api: api);
    await tester.pump();
    await tester.pump();
    await tester.pump();

    expect(gets, 1);
    expect(posts, 1);
    expect(find.text('octocat/project-aether'), findsOneWidget);
  });

  testWidgets('refreshed repositories replace the old list', (tester) async {
    final refresh = Completer<http.Response>();
    final api = _client((request) async {
      if (request.url.path.endsWith('/repositories/demo')) {
        return _json(_demo);
      }
      if (request.method == 'POST' &&
          request.url.path.endsWith('/authorized/refresh')) {
        return refresh.future;
      }
      if (request.url.path.endsWith('/repositories/authorized')) {
        return _json(_cached);
      }
      return _json({'detail': 'nope'}, 404);
    });

    await _pumpDashboard(tester, api: api);
    await tester.pump();
    await tester.pump();

    expect(find.text('octocat/circle_marketplace'), findsOneWidget);
    expect(find.text('1 repository is ready for issue triage.'), findsOneWidget);

    refresh.complete(_json(_refreshed));
    await tester.pump();
    await tester.pump();

    expect(find.text('octocat/circle_marketplace'), findsOneWidget);
    expect(find.text('octocat/project-aether'), findsOneWidget);
    expect(
      find.text('2 repositories are ready for issue triage.'),
      findsOneWidget,
    );
  });

  testWidgets('refresh failure preserves the existing list', (tester) async {
    final api = _client((request) async {
      if (request.url.path.endsWith('/repositories/demo')) {
        return _json(_demo);
      }
      if (request.method == 'POST' &&
          request.url.path.endsWith('/authorized/refresh')) {
        return _json({'detail': 'GitHub is unavailable'}, 502);
      }
      if (request.url.path.endsWith('/repositories/authorized')) {
        return _json(_cached);
      }
      return _json({'detail': 'nope'}, 404);
    });

    await _pumpDashboard(tester, api: api);
    await tester.pump();
    await tester.pump();
    await tester.pump();

    expect(find.text('octocat/circle_marketplace'), findsOneWidget);
    expect(find.text('1 connected'), findsOneWidget);
    expect(find.text('GitHub is unavailable'), findsNothing);
    expect(find.text('octocat/project-aether'), findsNothing);
  });

  testWidgets('?connected=1 does not cause duplicate refreshes', (tester) async {
    var gets = 0;
    var posts = 0;
    final api = _client((request) async {
      if (request.url.path.endsWith('/repositories/demo')) {
        return _json(_demo);
      }
      if (request.method == 'POST' &&
          request.url.path.endsWith('/authorized/refresh')) {
        posts += 1;
        return _json(_refreshed);
      }
      if (request.url.path.endsWith('/repositories/authorized')) {
        gets += 1;
        return _json(_cached);
      }
      return _json({'detail': 'nope'}, 404);
    });

    await _pumpDashboard(tester, api: api, refreshGrantsOnStart: true);
    await tester.pump();
    await tester.pump();
    await tester.pump();

    expect(gets, 1);
    expect(posts, 1);
    expect(find.text('octocat/project-aether'), findsOneWidget);
  });
}

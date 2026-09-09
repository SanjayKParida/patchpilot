import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:patchpilot_web/main.dart';
import 'package:patchpilot_web/services/api_client.dart';
import 'package:patchpilot_web/services/github_redirect.dart';

class _Redirect implements GithubRedirect {
  String? url;
  String? opened;

  @override
  void go(String value) => url = value;

  @override
  void open(String value) => opened = value;
}

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
  'private': false,
  'demo': true,
  'can_read': true,
  'can_write': false,
};

const _user = {
  'id': 'u1',
  'github_id': 4242,
  'github_login': 'octocat',
  'avatar_url': '',
  'name': 'The Octocat',
};

const _repos = [
  {
    'owner': 'octocat',
    'repo': 'private-app',
    'full_name': 'octocat/private-app',
    'private': true,
    'can_read': true,
    'can_write': true,
    'access': 'write',
  },
  {
    'owner': 'octocat',
    'repo': 'locked',
    'full_name': 'octocat/locked',
    'private': true,
    'can_read': false,
    'can_write': false,
    'access': 'none',
  },
];

ApiClient _client(Future<http.Response> Function(http.Request) handler) {
  return ApiClient(client: MockClient(handler));
}

Future<void> _pumpApp(
  WidgetTester tester, {
  required ApiClient api,
  GithubRedirect? redirect,
  bool? refreshGrantsOnStart,
  String? initialAuthError,
}) async {
  await tester.pumpWidget(
    PatchPilotApp(
      api: api,
      redirect: redirect,
      refreshGrantsOnStart: refreshGrantsOnStart,
      initialAuthError: initialAuthError,
    ),
  );
  await tester.pump();
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 50));
}

void main() {
  testWidgets('startup shows a loading state before auth resolves', (
    tester,
  ) async {
    final gate = Completer<http.Response>();
    final api = _client((request) {
      if (request.url.path.endsWith('/auth/me')) {
        return gate.future;
      }
      if (request.url.path.endsWith('/repositories/demo')) {
        return Future.value(_json(_demo));
      }
      return Future.value(_json({'detail': 'nope'}, 404));
    });

    await tester.pumpWidget(PatchPilotApp(api: api, redirect: _Redirect()));
    await tester.pump();

    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(find.text('SanjayKParida/patchpilot-diagnosis-demo'), findsNothing);
    expect(find.text('Connect GitHub'), findsNothing);

    gate.complete(_json({'authenticated': false, 'user': null}));
    await tester.pump();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(
      find.text('SanjayKParida/patchpilot-diagnosis-demo'),
      findsOneWidget,
    );
  });

  testWidgets('malformed session response still shows Demo', (tester) async {
    final api = _client((request) async {
      if (request.url.path.endsWith('/auth/me')) {
        return http.Response(
          'not-json',
          200,
          headers: const {'content-type': 'application/json; charset=utf-8'},
        );
      }
      if (request.url.path.endsWith('/repositories/demo')) {
        return _json(_demo);
      }
      return _json({'detail': 'nope'}, 404);
    });

    await _pumpApp(tester, api: api);

    expect(
      find.text('SanjayKParida/patchpilot-diagnosis-demo'),
      findsOneWidget,
    );
    expect(find.text('Connect GitHub'), findsWidgets);
  });

  testWidgets('unauthenticated startup still shows Demo', (tester) async {
    final api = _client((request) async {
      if (request.url.path.endsWith('/auth/me')) {
        return _json({'authenticated': false, 'user': null});
      }
      if (request.url.path.endsWith('/repositories/demo')) {
        return _json(_demo);
      }
      return _json({'detail': 'nope'}, 404);
    });

    await _pumpApp(tester, api: api);

    expect(find.text('DEMO'), findsWidgets);
    expect(
      find.text('SanjayKParida/patchpilot-diagnosis-demo'),
      findsOneWidget,
    );
    expect(find.text('Connect GitHub'), findsWidgets);
    expect(find.text('octocat'), findsNothing);
    expect(find.text('Log out'), findsNothing);
  });

  testWidgets('authenticated startup shows connected user and repos', (
    tester,
  ) async {
    final api = _client((request) async {
      if (request.url.path.endsWith('/auth/me')) {
        return _json({'authenticated': true, 'user': _user});
      }
      if (request.url.path.endsWith('/repositories/demo')) {
        return _json(_demo);
      }
      if (request.url.path.endsWith('/repositories/authorized')) {
        return _json(_repos);
      }
      return _json({'detail': 'nope'}, 404);
    });

    await _pumpApp(tester, api: api);

    expect(find.text('octocat'), findsOneWidget);
    expect(find.text('2 connected'), findsOneWidget);
    expect(find.text('Log out'), findsOneWidget);
    expect(
      find.text('SanjayKParida/patchpilot-diagnosis-demo'),
      findsOneWidget,
    );
    expect(find.text('octocat/private-app'), findsOneWidget);
    expect(find.text('WRITE'), findsOneWidget);
    expect(find.text('Connect GitHub'), findsNothing);
    expect(find.text('Manage GitHub access'), findsOneWidget);
  });

  testWidgets('Connect GitHub starts the authorization URL', (tester) async {
    final redirect = _Redirect();
    final api = _client((request) async {
      if (request.url.path.endsWith('/auth/me')) {
        return _json({'authenticated': false, 'user': null});
      }
      if (request.url.path.endsWith('/repositories/demo')) {
        return _json(_demo);
      }
      if (request.url.path.endsWith('/auth/github/login')) {
        return _json({
          'authorization_url':
              'https://github.com/login/oauth/authorize?client_id=iv1.test',
          'installation_url':
              'https://github.com/apps/patchpilot-dev/installations/new',
        });
      }
      return _json({'detail': 'nope'}, 404);
    });

    await _pumpApp(tester, api: api, redirect: redirect);
    await tester.tap(find.widgetWithText(FilledButton, 'Connect'));
    await tester.pump();
    await tester.pump();

    expect(
      redirect.url,
      'https://github.com/login/oauth/authorize?client_id=iv1.test',
    );
  });

  testWidgets('logout returns to the unauthenticated landing', (tester) async {
    var loggedIn = true;
    final api = _client((request) async {
      if (request.url.path.endsWith('/auth/me')) {
        if (!loggedIn) {
          return _json({'authenticated': false, 'user': null});
        }
        return _json({'authenticated': true, 'user': _user});
      }
      if (request.url.path.endsWith('/repositories/demo')) {
        return _json(_demo);
      }
      if (request.url.path.endsWith('/repositories/authorized')) {
        return _json(_repos);
      }
      if (request.method == 'POST' &&
          request.url.path.endsWith('/auth/logout')) {
        loggedIn = false;
        return _json({'ok': true});
      }
      return _json({'detail': 'nope'}, 404);
    });

    await _pumpApp(tester, api: api);
    expect(find.text('octocat'), findsOneWidget);

    await tester.tap(find.text('Log out'));
    await tester.pump();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text('octocat'), findsNothing);
    expect(find.widgetWithText(FilledButton, 'Connect'), findsOneWidget);
    expect(
      find.text('SanjayKParida/patchpilot-diagnosis-demo'),
      findsOneWidget,
    );
    expect(find.text('octocat/private-app'), findsNothing);
    expect(find.text('Manage GitHub access'), findsNothing);
  });

  testWidgets('refresh preserves login when /auth/me still has a session', (
    tester,
  ) async {
    final api = _client((request) async {
      if (request.url.path.endsWith('/auth/me')) {
        return _json({'authenticated': true, 'user': _user});
      }
      if (request.url.path.endsWith('/repositories/demo')) {
        return _json(_demo);
      }
      if (request.url.path.endsWith('/repositories/authorized')) {
        return _json(_repos);
      }
      return _json({'detail': 'nope'}, 404);
    });

    await _pumpApp(tester, api: api);
    expect(find.text('2 connected'), findsOneWidget);

    await tester.pumpWidget(const SizedBox.shrink());
    await _pumpApp(tester, api: api);

    expect(find.text('octocat'), findsOneWidget);
    expect(find.text('2 connected'), findsOneWidget);
    expect(find.text('octocat/private-app'), findsOneWidget);
  });

  testWidgets('repositories are prioritized above the demo', (tester) async {
    final api = _client((request) async {
      if (request.url.path.endsWith('/auth/me')) {
        return _json({'authenticated': false, 'user': null});
      }
      if (request.url.path.endsWith('/repositories/demo')) {
        return _json(_demo);
      }
      return _json({'detail': 'nope'}, 404);
    });

    await _pumpApp(tester, api: api);

    final connect = tester.getTopLeft(
      find.widgetWithText(FilledButton, 'Connect'),
    );
    final demo = tester.getTopLeft(
      find.text('SanjayKParida/patchpilot-diagnosis-demo'),
    );
    expect(connect.dy, lessThan(demo.dy));
  });

  testWidgets('unauthorized repositories are not tappable', (tester) async {
    final api = _client((request) async {
      if (request.url.path.endsWith('/auth/me')) {
        return _json({'authenticated': true, 'user': _user});
      }
      if (request.url.path.endsWith('/repositories/demo')) {
        return _json(_demo);
      }
      if (request.url.path.endsWith('/repositories/authorized')) {
        return _json(_repos);
      }
      return _json({'detail': 'nope'}, 404);
    });

    await _pumpApp(tester, api: api);

    expect(find.text('octocat/locked'), findsOneWidget);
    expect(find.text('NO ACCESS'), findsOneWidget);

    await tester.tap(find.text('octocat/locked'));
    await tester.pump();

    expect(
      find.text('SanjayKParida/patchpilot-diagnosis-demo'),
      findsOneWidget,
    );
    expect(find.text('octocat/private-app'), findsOneWidget);
  });

  testWidgets('authenticated with no repositories shows Select repositories', (
    tester,
  ) async {
    final redirect = _Redirect();
    final api = _client((request) async {
      if (request.url.path.endsWith('/auth/me')) {
        return _json({'authenticated': true, 'user': _user});
      }
      if (request.url.path.endsWith('/repositories/demo')) {
        return _json(_demo);
      }
      if (request.url.path.endsWith('/repositories/authorized')) {
        return _json([]);
      }
      if (request.url.path.endsWith('/auth/github/install')) {
        return _json({
          'installation_url':
              'https://github.com/apps/patchpilot-dev/installations/new',
        });
      }
      return _json({'detail': 'nope'}, 404);
    });

    await _pumpApp(tester, api: api, redirect: redirect);

    expect(find.text('No repositories selected'), findsOneWidget);
    expect(
      find.text('Choose repositories from your GitHub installation.'),
      findsOneWidget,
    );
    expect(
      find.widgetWithText(FilledButton, 'Select repositories'),
      findsOneWidget,
    );
    expect(
      find.textContaining('Install PatchPilot on the accounts'),
      findsNothing,
    );
    expect(
      find.text('SanjayKParida/patchpilot-diagnosis-demo'),
      findsOneWidget,
    );
    expect(find.text('Manage GitHub access'), findsNothing);
    expect(find.text('octocat'), findsOneWidget);

    await tester.tap(find.widgetWithText(FilledButton, 'Select repositories'));
    await tester.pump();
    await tester.pump();
    expect(
      redirect.url,
      'https://github.com/apps/patchpilot-dev/installations/new',
    );
  });

  testWidgets('Manage GitHub access opens the installation URL', (
    tester,
  ) async {
    final redirect = _Redirect();
    final api = _client((request) async {
      if (request.url.path.endsWith('/auth/me')) {
        return _json({'authenticated': true, 'user': _user});
      }
      if (request.url.path.endsWith('/repositories/demo')) {
        return _json(_demo);
      }
      if (request.url.path.endsWith('/repositories/authorized')) {
        return _json(_repos);
      }
      if (request.url.path.endsWith('/auth/github/install')) {
        return _json({
          'installation_url':
              'https://github.com/apps/patchpilot-dev/installations/new',
        });
      }
      return _json({'detail': 'nope'}, 404);
    });

    await _pumpApp(tester, api: api, redirect: redirect);
    await tester.ensureVisible(find.text('Manage GitHub access'));
    await tester.tap(find.text('Manage GitHub access'));
    await tester.pump();
    await tester.pump();
    expect(
      redirect.url,
      'https://github.com/apps/patchpilot-dev/installations/new',
    );
  });

  testWidgets('post-install return refreshes authorized repositories', (
    tester,
  ) async {
    var refreshed = false;
    final api = _client((request) async {
      if (request.url.path.endsWith('/auth/me')) {
        return _json({'authenticated': true, 'user': _user});
      }
      if (request.url.path.endsWith('/repositories/demo')) {
        return _json(_demo);
      }
      if (request.url.path.endsWith('/authorized/refresh')) {
        refreshed = true;
        return _json(_repos);
      }
      if (request.url.path.endsWith('/repositories/authorized')) {
        return _json([]);
      }
      return _json({'detail': 'nope'}, 404);
    });

    await _pumpApp(tester, api: api, refreshGrantsOnStart: true);

    expect(refreshed, isTrue);
    expect(find.text('octocat/private-app'), findsOneWidget);
    expect(find.text('No repositories selected'), findsNothing);
  });

  testWidgets('authorization error keeps Demo usable', (tester) async {
    final api = _client((request) async {
      if (request.url.path.endsWith('/auth/me')) {
        return _json({'authenticated': false, 'user': null});
      }
      if (request.url.path.endsWith('/repositories/demo')) {
        return _json(_demo);
      }
      return _json({'detail': 'nope'}, 404);
    });

    await _pumpApp(
      tester,
      api: api,
      initialAuthError: 'GitHub authorization failed',
    );

    expect(find.text('GitHub authorization failed'), findsOneWidget);
    expect(find.text('Try again'), findsOneWidget);
    expect(
      find.text('SanjayKParida/patchpilot-diagnosis-demo'),
      findsOneWidget,
    );
    expect(find.widgetWithText(FilledButton, 'Connect'), findsOneWidget);
  });

  testWidgets('repository search filters the authorized list', (tester) async {
    final api = _client((request) async {
      if (request.url.path.endsWith('/auth/me')) {
        return _json({'authenticated': true, 'user': _user});
      }
      if (request.url.path.endsWith('/repositories/demo')) {
        return _json(_demo);
      }
      if (request.url.path.endsWith('/repositories/authorized')) {
        return _json(_repos);
      }
      return _json({'detail': 'nope'}, 404);
    });

    await _pumpApp(tester, api: api);
    await tester.enterText(find.byType(TextField), 'private');
    await tester.pump();

    expect(find.text('octocat/private-app'), findsOneWidget);
    expect(find.text('octocat/locked'), findsNothing);
  });

  testWidgets('selecting a repository opens the issue list', (tester) async {
    final api = _client((request) async {
      if (request.url.path.endsWith('/auth/me')) {
        return _json({'authenticated': true, 'user': _user});
      }
      if (request.url.path.endsWith('/repositories/demo')) {
        return _json(_demo);
      }
      if (request.url.path.endsWith('/repositories/authorized')) {
        return _json(_repos);
      }
      if (request.url.path.endsWith('/issues')) {
        return _json([]);
      }
      if (request.url.path.endsWith('/snapshot')) {
        return _json({
          'commit_sha': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
          'status': 'ready',
          'file_count': 12,
        });
      }
      return _json({'detail': 'nope'}, 404);
    });

    await _pumpApp(tester, api: api);
    await tester.tap(find.text('octocat/private-app'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));

    expect(find.text('This repository has no open issues.'), findsOneWidget);
    expect(
      find.text('Commit SHA or ref (optional). Leave blank for current HEAD.'),
      findsOneWidget,
    );
    expect(find.text('SanjayKParida/patchpilot-diagnosis-demo'), findsNothing);
  });
}

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:patchpilot_web/app/oauth_return.dart';
import 'package:patchpilot_web/services/api_client.dart';

void main() {
  test('startGithubLogin receives explicit repairPath and repair return_to', () async {
    Uri? seen;
    final api = ApiClient(
      client: MockClient((request) async {
        seen = request.url;
        return http.Response(
          jsonEncode({'authorization_url': 'https://github.com/login'}),
          200,
          headers: const {'content-type': 'application/json; charset=utf-8'},
        );
      }),
    );

    const repairPath = '/r/owner/repo/issues/1/pull-request';
    final login = oauthGithubLogin(
      page: Uri.parse('http://localhost:59738/'),
      route: Uri.parse('/'),
      analysisId: 'a1',
      stage: 'pull-request',
      repairPath: repairPath,
    );

    await api.startGithubLogin(
      returnTo: login.returnTo,
      analysisId: login.analysisId,
      stage: login.stage,
      repairPath: login.repairPath,
    );

    expect(seen, isNotNull);
    expect(seen!.queryParameters['repair_path'], repairPath);
    expect(seen!.queryParameters['analysis_id'], 'a1');
    expect(seen!.queryParameters['stage'], 'pull-request');
    expect(seen!.queryParameters['return_to'], contains(repairPath));
    expect(login.returnTo, contains(repairPath));
  });
}

import 'package:flutter_test/flutter_test.dart';
import 'package:patchpilot_web/app/oauth_return.dart';

void main() {
  test('oauthReturnTo keeps the current repair path', () {
    final url = oauthReturnTo(
      page: Uri.parse('http://localhost:59738/'),
      route: Uri.parse('/r/owner/repo/issues/1/diagnosis'),
    );

    expect(
      url,
      'http://localhost:59738/r/owner/repo/issues/1/diagnosis',
    );
  });

  test('oauthReturnTo carries analysis_id for OAuth resume', () {
    final url = oauthReturnTo(
      page: Uri.parse('http://localhost:59738/'),
      route: Uri.parse('/r/owner/repo/issues/1/pull-request'),
      analysisId: 'a1',
    );

    expect(
      url,
      'http://localhost:59738/r/owner/repo/issues/1/pull-request?analysis_id=a1',
    );
  });

  test('oauthAnalysisId reads the resume query', () {
    expect(
      oauthAnalysisId(Uri.parse('/r/o/r/issues/1/diagnosis?analysis_id=a1')),
      'a1',
    );
    expect(oauthAnalysisId(Uri.parse('/r/o/r/issues/1/diagnosis')), isNull);
  });

  test('oauthReturnTo keeps ref query and drops connected', () {
    final url = oauthReturnTo(
      page: Uri.parse('http://localhost:59738/?connected=1'),
      route: Uri.parse('/r/owner/repo/issues/1/patch?ref=abc'),
    );

    expect(
      url,
      'http://localhost:59738/r/owner/repo/issues/1/patch?ref=abc',
    );
  });

  test('oauthRepairPath is null on the dashboard', () {
    expect(oauthRepairPath(Uri.parse('/')), isNull);
    expect(
      oauthRepairPath(Uri.parse('/r/owner/repo/issues/1/diagnosis')),
      '/r/owner/repo/issues/1/diagnosis',
    );
  });

  test('oauthResolvedRepairPath prefers an explicit path over /', () {
    const repairPath = '/r/owner/repo/issues/1/pull-request?ref=abc';
    expect(
      oauthResolvedRepairPath(repairPath, Uri.parse('/')),
      repairPath,
    );
    expect(oauthResolvedRepairPath(null, Uri.parse('/')), isNull);
    expect(oauthResolvedRepairPath('', Uri.parse('/')), isNull);
    expect(
      oauthResolvedRepairPath(
        null,
        Uri.parse('/r/owner/repo/issues/1/diagnosis'),
      ),
      '/r/owner/repo/issues/1/diagnosis',
    );
  });

  test('oauthGithubLogin prefers explicit repairPath over a dashboard route', () {
    final login = oauthGithubLogin(
      page: Uri.parse('http://localhost:59738/'),
      route: Uri.parse('/'),
      analysisId: 'a1',
      stage: 'pull-request',
      repairPath: '/r/owner/repo/issues/1/pull-request?ref=abc',
    );

    expect(
      login.repairPath,
      '/r/owner/repo/issues/1/pull-request?ref=abc',
    );
    expect(login.analysisId, 'a1');
    expect(login.stage, 'pull-request');
    final returnTo = Uri.parse(login.returnTo!);
    expect(returnTo.path, '/r/owner/repo/issues/1/pull-request');
    expect(returnTo.queryParameters['analysis_id'], 'a1');
    expect(returnTo.queryParameters['ref'], 'abc');
  });

  test('oauthGithubLogin without repairPath stays on the dashboard', () {
    final login = oauthGithubLogin(
      page: Uri.parse('http://localhost:59738/'),
      route: Uri.parse('/'),
    );

    expect(login.repairPath, isNull);
    expect(login.analysisId, isNull);
    expect(login.stage, isNull);
    expect(login.returnTo, 'http://localhost:59738/');
  });

  test('oauthGithubLogin still forwards analysisId and stage from the route', () {
    final login = oauthGithubLogin(
      page: Uri.parse('http://localhost:59738/'),
      route: Uri.parse('/r/owner/repo/issues/1/diagnosis?analysis_id=a1'),
    );

    expect(login.analysisId, 'a1');
    expect(login.stage, 'diagnosis');
    expect(
      login.repairPath,
      '/r/owner/repo/issues/1/diagnosis?analysis_id=a1',
    );
  });

  test('oauthStage reads the repair URL segment', () {
    expect(
      oauthStage(Uri.parse('/r/owner/repo/issues/1/pull-request')),
      'pull-request',
    );
    expect(oauthStage(Uri.parse('/')), isNull);
  });
}

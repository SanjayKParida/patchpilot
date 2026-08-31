import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:patchpilot_web/services/api_client.dart';
import 'package:patchpilot_web/services/key_value_store.dart';
import 'package:patchpilot_web/services/session_token.dart';

void main() {
  test('reads a 32-character session id from the OAuth fragment', () {
    expect(
      sessionIdFromFragment('#session=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'),
      'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    );
  });

  test('rejects a fragment that is not a session id', () {
    expect(sessionIdFromFragment(''), isNull);
    expect(sessionIdFromFragment('#other=1'), isNull);
    expect(sessionIdFromFragment('#session=not-a-session'), isNull);
    expect(sessionIdFromFragment('#session=ghu_notthis'), isNull);
  });

  test('hot restart sends the stored session as a bearer token', () async {
    final tokens = MemoryKeyValueStore();
    tokens.write(sessionStorageKey, 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb');
    String? authorization;

    final api = ApiClient(
      tokens: tokens,
      client: MockClient((request) async {
        authorization = request.headers['Authorization'];
        return http.Response(
          '{"authenticated":true,"user":{"id":"u1","github_id":1,'
          '"github_login":"octocat","avatar_url":"","name":""}}',
          200,
          headers: const {'content-type': 'application/json; charset=utf-8'},
        );
      }),
    );

    final me = await api.getMe();

    expect(me.authenticated, isTrue);
    expect(authorization, 'Bearer bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb');
  });

  test('logout drops the stored session token', () async {
    final tokens = MemoryKeyValueStore();
    tokens.write(sessionStorageKey, 'cccccccccccccccccccccccccccccccc');
    final api = ApiClient(
      tokens: tokens,
      client: MockClient((request) async {
        return http.Response(
          '{"ok":true}',
          200,
          headers: const {'content-type': 'application/json; charset=utf-8'},
        );
      }),
    );

    await api.logout();

    expect(tokens.read(sessionStorageKey), isNull);
  });
}

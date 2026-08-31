import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:patchpilot_web/services/api_client.dart';

Map<String, dynamic> _proposalJson() {
  return {
    'status': 'ok',
    'summary': 'emit loaded state after refresh',
    'reasoning': 'Refresh handler never leaves TaskLoading.',
    'confidence': 0.9,
    'warnings': <String>[],
    'errors': <String>[],
    'files': [
      {
        'path': 'lib/bloc/task_bloc.dart',
        'language': 'dart',
        'hunks': [
          {
            'start_line': 2,
            'end_line': 2,
            'old_text': '  // missing emit',
            'new_text': '  emit(TaskLoaded());',
          },
        ],
      },
    ],
  };
}

http.Response _json(Object body, int status) {
  return http.Response(
    jsonEncode(body),
    status,
    headers: const {'content-type': 'application/json; charset=utf-8'},
  );
}

void main() {
  test('generatePatch waits 180s, matching validate and deliver', () {
    expect(ApiClient.patchGenerateTimeout, const Duration(seconds: 180));
  });

  test('normal generation completes within the generate timeout', () async {
    var posts = 0;
    var gets = 0;
    final api = ApiClient(
      client: MockClient((request) async {
        if (request.method == 'POST') {
          posts += 1;
          await Future<void>.delayed(const Duration(milliseconds: 20));
          return _json(_proposalJson(), 200);
        }
        gets += 1;
        return _json({'detail': 'unexpected GET'}, 500);
      }),
    );

    final proposal = await api.generatePatch(
      'analysis-1',
      timeout: const Duration(seconds: 2),
    );

    expect(proposal.isOk, isTrue);
    expect(proposal.summary, 'emit loaded state after refresh');
    expect(posts, 1);
    expect(gets, 0);
  });

  test('slow LLM response still returns 200 within the generate timeout',
      () async {
    final api = ApiClient(
      client: MockClient((request) async {
        await Future<void>.delayed(const Duration(milliseconds: 80));
        return _json(_proposalJson(), 200);
      }),
    );

    final proposal = await api.generatePatch(
      'analysis-1',
      timeout: const Duration(milliseconds: 500),
    );

    expect(proposal.isOk, isTrue);
  });

  test('cached proposal is returned without treating it as a timeout',
      () async {
    var posts = 0;
    final api = ApiClient(
      client: MockClient((request) async {
        if (request.method == 'POST') {
          posts += 1;
          return _json(_proposalJson(), 200);
        }
        fail('cached generate should not poll GET');
      }),
    );

    final proposal = await api.generatePatch('analysis-1');

    expect(proposal.isOk, isTrue);
    expect(posts, 1);
  });

  test('409 running then GET success does not start another generation',
      () async {
    var posts = 0;
    var gets = 0;
    final api = ApiClient(
      client: MockClient((request) async {
        if (request.method == 'POST') {
          posts += 1;
          return _json(
            {
              'detail':
                  'Patch generation is already running for this analysis',
            },
            409,
          );
        }
        gets += 1;
        if (gets < 2) {
          return _json(
            {
              'detail':
                  'Patch generation is already running for this analysis',
            },
            409,
          );
        }
        return _json(_proposalJson(), 200);
      }),
    );

    final proposal = await api.generatePatch(
      'analysis-1',
      timeout: const Duration(seconds: 2),
      pollInterval: const Duration(milliseconds: 1),
    );

    expect(proposal.isOk, isTrue);
    expect(posts, 1);
    expect(gets, 2);
  });

  test('client timeout recovers a proposal stored after the POST gave up',
      () async {
    var posts = 0;
    var gets = 0;
    final api = ApiClient(
      client: MockClient((request) async {
        if (request.method == 'POST') {
          posts += 1;
          await Future<void>.delayed(const Duration(milliseconds: 80));
          return _json(_proposalJson(), 200);
        }
        gets += 1;
        return _json(_proposalJson(), 200);
      }),
    );

    final proposal = await api.generatePatch(
      'analysis-1',
      timeout: const Duration(milliseconds: 10),
      pollInterval: const Duration(milliseconds: 1),
    );

    expect(proposal.isOk, isTrue);
    expect(posts, 1);
    expect(gets, greaterThanOrEqualTo(1));
  });

  test('connection drop during POST polls for the stored proposal', () async {
    var posts = 0;
    var gets = 0;
    final api = ApiClient(
      client: MockClient((request) async {
        if (request.method == 'POST') {
          posts += 1;
          throw Exception('connection abort');
        }
        gets += 1;
        return _json(_proposalJson(), 200);
      }),
    );

    final proposal = await api.generatePatch(
      'analysis-1',
      timeout: const Duration(seconds: 2),
      pollInterval: const Duration(milliseconds: 1),
    );

    expect(proposal.isOk, isTrue);
    expect(posts, 1);
    expect(gets, 1);
  });

  test('timeout is shown only when generation never completes', () async {
    final api = ApiClient(
      client: MockClient((request) async {
        if (request.method == 'POST') {
          await Future<void>.delayed(const Duration(milliseconds: 200));
          return _json(_proposalJson(), 200);
        }
        return _json(
          {
            'detail':
                'Patch generation is already running for this analysis',
          },
          409,
        );
      }),
    );

    await expectLater(
      api.generatePatch(
        'analysis-1',
        timeout: const Duration(milliseconds: 40),
        pollInterval: const Duration(milliseconds: 5),
      ),
      throwsA(
        isA<ApiException>().having(
          (error) => error.message,
          'message',
          'The API did not respond in time.',
        ),
      ),
    );
  });

  test('generator failure remains distinguishable from HTTP timeout', () async {
    var gets = 0;
    final api = ApiClient(
      client: MockClient((request) async {
        if (request.method == 'POST') {
          return _json(
            {'detail': 'Patch generation failed: llm exploded'},
            502,
          );
        }
        gets += 1;
        return _json({'detail': 'should not poll'}, 500);
      }),
    );

    await expectLater(
      api.generatePatch('analysis-1'),
      throwsA(
        isA<ApiException>()
            .having((error) => error.statusCode, 'status', 502)
            .having(
              (error) => error.message,
              'message',
              contains('llm exploded'),
            ),
      ),
    );
    expect(gets, 0);
  });
}

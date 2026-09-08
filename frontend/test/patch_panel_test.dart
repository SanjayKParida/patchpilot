import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:patchpilot_web/services/api_client.dart';
import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/features/repair/patch/widgets/patch_panel.dart';

Map<String, dynamic> _hunk({
  int start = 2,
  int end = 2,
  String oldText = '  // missing emit',
  String newText = '  emit(TaskLoaded());',
}) {
  return {
    'start_line': start,
    'end_line': end,
    'old_text': oldText,
    'new_text': newText,
  };
}

Map<String, dynamic> _proposalJson({
  String status = 'ok',
  String summary = 'emit loaded state after refresh',
  String reasoning = 'Refresh handler never leaves TaskLoading.',
  List<Map<String, dynamic>>? files,
  List<String> warnings = const [],
  List<String> errors = const [],
}) {
  return {
    'status': status,
    'summary': summary,
    'reasoning': reasoning,
    'confidence': 0.9,
    'warnings': warnings,
    'errors': errors,
    'files':
        files ??
        [
          {
            'path': 'lib/bloc/task_bloc.dart',
            'language': 'dart',
            'hunks': [_hunk()],
          },
        ],
  };
}

Map<String, dynamic> _validationJson({
  String status = 'passed',
  bool applied = true,
  bool passed = true,
  bool runnable = true,
  String unavailable = '',
  List<Map<String, dynamic>>? commands,
  List<String> errors = const [],
  List<String> warnings = const [],
}) {
  return {
    'status': status,
    'applied': applied,
    'validation_passed': passed,
    'runnable': runnable,
    'unavailable_reason': unavailable,
    'errors': errors,
    'warnings': warnings,
    'commands':
        commands ??
        [
          {
            'name': 'pub_get',
            'argv': ['flutter', 'pub', 'get'],
            'exit_code': 0,
            'timed_out': false,
            'stdout': '',
            'stderr': '',
            'duration_ms': 10,
          },
          {
            'name': 'analyze',
            'argv': ['flutter', 'analyze'],
            'exit_code': 0,
            'timed_out': false,
            'stdout': '',
            'stderr': '',
            'duration_ms': 20,
          },
          {
            'name': 'test',
            'argv': ['flutter', 'test'],
            'exit_code': 0,
            'timed_out': false,
            'stdout': '',
            'stderr': '',
            'duration_ms': 30,
          },
        ],
  };
}

class _Script {
  Map<String, dynamic>? getPatch;
  int getPatchStatus = 502;
  int getPatchCalls = 0;
  int getPatchReadyAfter = 0;
  Map<String, dynamic>? postPatch;
  int postPatchStatus = 200;
  String? postPatchDetail;
  Completer<http.Response>? generateGate;
  Map<String, dynamic>? getValidation;
  int getValidationStatus = 502;
  Map<String, dynamic>? postValidation;
  int postValidationStatus = 200;
  Map<String, dynamic>? getApproval;
  int getApprovalStatus = 404;
  Map<String, dynamic>? postApproval;
  int postApprovalStatus = 200;
  Map<String, dynamic>? getDelivery;
  int getDeliveryStatus = 404;
  Map<String, dynamic>? postDelivery;
  int postDeliveryStatus = 200;
  String? postDeliveryDetail;
  Completer<http.Response>? validateGate;
  Completer<http.Response>? deliverGate;

  int generateCalls = 0;
  int validateCalls = 0;
  int approveCalls = 0;
  int deliverCalls = 0;
}

Map<String, dynamic> _approvalJson({
  String sha = 'f0bfc5b317f4984dc2c8d253715e9a30c72c0a5c',
}) {
  return {
    'approved': true,
    'approved_at': '2026-08-30T12:00:00+00:00',
    'commit_sha': sha,
    'analysis_id': 'a1',
  };
}

Map<String, dynamic> _deliveryJson({
  String status = 'succeeded',
  String stage = 'pull_request',
  String? branch = 'patchpilot/issue-3/f0bfc5b317f4-aaaaaaaa',
  String? commitSha = 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
  String base = 'f0bfc5b317f4984dc2c8d253715e9a30c72c0a5c',
  int? prNumber = 12,
  String? prUrl = 'https://github.com/owner/repo/pull/12',
  bool draft = true,
  List<String> errors = const [],
  List<String> warnings = const [],
}) {
  return {
    'status': status,
    'stage': stage,
    'branch': branch,
    'commit_sha': commitSha,
    'base_commit_sha': base,
    'pr_number': prNumber,
    'pr_url': prUrl,
    'draft': draft,
    'errors': errors,
    'warnings': warnings,
  };
}

http.Response _json(Object? body, int status) {
  return http.Response(
    jsonEncode(body),
    status,
    headers: const {'content-type': 'application/json; charset=utf-8'},
  );
}

ApiClient _client(_Script script) {
  return ApiClient(
    client: MockClient((request) async {
      final path = request.url.path;
      final isDeliver = path.endsWith('/patch/deliver');
      final isApprove = path.endsWith('/patch/approve');
      final isValidate = path.endsWith('/patch/validate');
      final isPatch = path.endsWith('/patch');

      if (request.method == 'GET' && isDeliver) {
        if (script.getDelivery == null) {
          return _json({
            'detail': 'No patch delivery has been attempted',
          }, script.getDeliveryStatus);
        }
        return _json(script.getDelivery, script.getDeliveryStatus);
      }

      if (request.method == 'POST' && isDeliver) {
        script.deliverCalls += 1;
        if (script.deliverGate != null) {
          return script.deliverGate!.future;
        }
        if (script.postDeliveryStatus >= 400) {
          return _json({
            'detail': script.postDeliveryDetail ?? 'Delivery failed',
          }, script.postDeliveryStatus);
        }
        return _json(
          script.postDelivery ?? _deliveryJson(),
          script.postDeliveryStatus,
        );
      }

      if (request.method == 'GET' && isApprove) {
        if (script.getApproval == null) {
          return _json({
            'detail': 'This patch has not been approved',
          }, script.getApprovalStatus);
        }
        return _json(script.getApproval, script.getApprovalStatus);
      }

      if (request.method == 'POST' && isApprove) {
        script.approveCalls += 1;
        if (script.postApprovalStatus >= 400) {
          return _json({
            'detail': 'The patch has not been validated',
          }, script.postApprovalStatus);
        }
        return _json(
          script.postApproval ?? _approvalJson(),
          script.postApprovalStatus,
        );
      }

      if (request.method == 'GET' && isValidate) {
        if (script.getValidation == null) {
          return _json({
            'detail': 'No patch validation is available',
          }, script.getValidationStatus);
        }
        return _json(script.getValidation, script.getValidationStatus);
      }

      if (request.method == 'POST' && isValidate) {
        script.validateCalls += 1;
        if (script.validateGate != null) {
          return script.validateGate!.future;
        }
        return _json(
          script.postValidation ?? _validationJson(),
          script.postValidationStatus,
        );
      }

      if (request.method == 'GET' && isPatch) {
        script.getPatchCalls += 1;
        if (script.getPatch != null) {
          return _json(script.getPatch, script.getPatchStatus);
        }
        if (script.getPatchReadyAfter > 0 &&
            script.getPatchCalls >= script.getPatchReadyAfter) {
          return _json(_proposalJson(), 200);
        }
        final detail = script.getPatchStatus == 409
            ? 'Patch generation is already running for this analysis'
            : 'No patch proposal is available';
        return _json({'detail': detail}, script.getPatchStatus);
      }

      if (request.method == 'POST' && isPatch) {
        script.generateCalls += 1;
        if (script.generateGate != null) {
          return script.generateGate!.future;
        }
        if (script.postPatchStatus >= 400) {
          return _json({
            'detail': script.postPatchDetail ?? 'Patch generation failed',
          }, script.postPatchStatus);
        }
        return _json(
          script.postPatch ?? _proposalJson(),
          script.postPatchStatus,
        );
      }

      return http.Response('unexpected ${request.method} $path', 500);
    }),
  );
}

Future<void> _pump(
  WidgetTester tester,
  ApiClient api, {
  void Function(String path, {int? line, String? reason})? onOpen,
  String? commitSha,
  String? requestedRef,
}) {
  tester.view.physicalSize = const Size(800, 2600);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);

  return tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.build(),
      home: Scaffold(
        body: SingleChildScrollView(
          child: PatchPanel(
            api: api,
            analysisId: 'a1',
            commitSha: commitSha,
            requestedRef: requestedRef,
            onOpenFile: onOpen ?? (path, {int? line, String? reason}) {},
          ),
        ),
      ),
    ),
  );
}

Future<void> _settle(WidgetTester tester) async {
  await tester.pump();
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('full review flow: generate, inspect diff, validate, approve', (
    tester,
  ) async {
    final script = _Script()
      ..postPatch = _proposalJson()
      ..postValidation = _validationJson();

    await _pump(tester, _client(script));
    await _settle(tester);

    expect(find.text('Approve patch'), findsNothing);

    await tester.tap(find.text('Generate patch'));
    await _settle(tester);

    expect(find.text('Generated'), findsOneWidget);
    expect(find.text('90% confidence'), findsOneWidget);
    expect(find.text('lib/bloc/task_bloc.dart'), findsOneWidget);
    expect(find.textContaining('@@ 2,2 @@'), findsOneWidget);
    expect(find.textContaining('missing emit'), findsOneWidget);
    expect(find.textContaining('emit(TaskLoaded())'), findsOneWidget);
    expect(find.text('Not validated'), findsOneWidget);
    expect(find.text('Approve patch'), findsNothing);

    await tester.tap(find.text('Validate patch'));
    await _settle(tester);

    expect(find.text('Validation passed'), findsOneWidget);
    expect(find.text('Patch applied'), findsOneWidget);
    expect(find.text('flutter pub get'), findsOneWidget);
    expect(find.text('exit 0'), findsNWidgets(3));
    expect(find.text('lib/bloc/task_bloc.dart'), findsOneWidget);

    await tester.ensureVisible(find.text('Approve patch'));
    await tester.tap(find.text('Approve patch'));
    await _settle(tester);

    expect(script.approveCalls, 1);
    expect(find.text('Patch approved'), findsOneWidget);
    expect(find.text('Create draft PR'), findsOneWidget);
    expect(
      find.textContaining('Opening a draft pull request is a separate step'),
      findsOneWidget,
    );

    await tester.ensureVisible(find.text('Create draft PR'));
    await tester.tap(find.text('Create draft PR'));
    await _settle(tester);

    expect(script.deliverCalls, 1);
    expect(find.text('Draft PR opened'), findsOneWidget);
    expect(find.text('https://github.com/owner/repo/pull/12'), findsOneWidget);
    expect(find.textContaining('Pull request #12'), findsOneWidget);
    expect(find.text('Create draft PR'), findsNothing);
  });

  testWidgets('generate patch success renders the proposal diff', (
    tester,
  ) async {
    final script = _Script()..postPatch = _proposalJson();

    await _pump(tester, _client(script));
    await _settle(tester);

    expect(find.text('Generate patch'), findsOneWidget);
    expect(find.text('No patch yet'), findsOneWidget);
    expect(find.textContaining('Generate a patch to preview'), findsOneWidget);
    expect(find.text('Approve patch'), findsNothing);

    await tester.tap(find.text('Generate patch'));
    await _settle(tester);

    expect(script.generateCalls, 1);
    expect(find.text('Generated'), findsOneWidget);
    expect(find.text('90% confidence'), findsOneWidget);
    expect(find.text('emit loaded state after refresh'), findsOneWidget);
    expect(find.text('lib/bloc/task_bloc.dart'), findsOneWidget);
    expect(find.textContaining('@@ 2,2 @@'), findsOneWidget);
    expect(find.textContaining('missing emit'), findsOneWidget);
    expect(find.textContaining('emit(TaskLoaded())'), findsOneWidget);
    expect(find.text('Not validated'), findsOneWidget);
    expect(find.text('Approve patch'), findsNothing);
  });

  testWidgets('double tap generate does not start a second request', (
    tester,
  ) async {
    final gate = Completer<http.Response>();
    final script = _Script()
      ..postPatch = _proposalJson()
      ..generateGate = gate;

    await _pump(tester, _client(script));
    await _settle(tester);

    await tester.tap(find.text('Generate patch'));
    await tester.tap(find.text('Generate patch'));
    await tester.pump();

    expect(script.generateCalls, 1);
    expect(find.text('Generate patch'), findsNothing);

    gate.complete(_json(_proposalJson(), 200));
    await _settle(tester);

    expect(script.generateCalls, 1);
    expect(find.text('Generated'), findsOneWidget);
  });

  testWidgets(
    'generate waits for an in-progress proposal instead of erroring',
    (tester) async {
      final script = _Script()
        ..postPatchStatus = 409
        ..postPatchDetail =
            'Patch generation is already running for this analysis'
        ..getPatchStatus = 409
        ..getPatchReadyAfter = 2;

      await _pump(tester, _client(script));
      await _settle(tester);

      expect(find.text('Generate patch'), findsOneWidget);

      await tester.tap(find.text('Generate patch'));
      await _settle(tester);

      expect(script.generateCalls, 1);
      expect(find.text('Generated'), findsOneWidget);
      expect(find.text('The API did not respond in time.'), findsNothing);
    },
  );

  testWidgets('in-progress cached GET is not shown as a timeout', (
    tester,
  ) async {
    final script = _Script()..getPatchStatus = 409;

    await _pump(tester, _client(script));
    await _settle(tester);

    expect(find.text('The API did not respond in time.'), findsNothing);
    expect(find.textContaining('already running'), findsNothing);
    expect(find.text('Generate patch'), findsOneWidget);
  });

  testWidgets('cached patch retrieval shows the stored proposal', (
    tester,
  ) async {
    final script = _Script()
      ..getPatch = _proposalJson()
      ..getPatchStatus = 200;

    await _pump(tester, _client(script));
    await _settle(tester);

    expect(find.text('Generate patch'), findsNothing);
    expect(find.text('emit loaded state after refresh'), findsOneWidget);
    expect(script.generateCalls, 0);
  });

  testWidgets('renders a multi-file patch grouped by path', (tester) async {
    final script = _Script()
      ..getPatch = _proposalJson(
        files: [
          {
            'path': 'lib/bloc/task_bloc.dart',
            'language': 'dart',
            'hunks': [_hunk()],
          },
          {
            'path': 'lib/pages/home_page.dart',
            'language': 'dart',
            'hunks': [
              _hunk(
                start: 8,
                end: 8,
                oldText: '  return [];',
                newText: '  return tasks;',
              ),
            ],
          },
        ],
      )
      ..getPatchStatus = 200;

    await _pump(tester, _client(script));
    await _settle(tester);

    expect(find.text('lib/bloc/task_bloc.dart'), findsOneWidget);
    expect(find.text('lib/pages/home_page.dart'), findsOneWidget);
    expect(find.textContaining('return [];'), findsOneWidget);
    expect(find.textContaining('return tasks;'), findsOneWidget);
  });

  testWidgets('shows proposal warnings and errors', (tester) async {
    final script = _Script()
      ..getPatch = _proposalJson(
        warnings: ['narrow context around TaskBloc'],
        errors: ['hunk overlaps another edit'],
      )
      ..getPatchStatus = 200;

    await _pump(tester, _client(script));
    await _settle(tester);

    expect(find.text('narrow context around TaskBloc'), findsOneWidget);
    expect(find.text('hunk overlaps another edit'), findsOneWidget);
  });

  testWidgets('insufficient context explains why no patch was produced', (
    tester,
  ) async {
    final script = _Script()
      ..getPatch = _proposalJson(
        status: 'insufficient_context',
        summary: 'not enough surrounding code',
        files: const [],
      )
      ..getPatchStatus = 200;

    await _pump(tester, _client(script));
    await _settle(tester);

    expect(find.text('Insufficient context'), findsOneWidget);
    expect(
      find.textContaining('could not safely produce a patch'),
      findsOneWidget,
    );
    expect(find.text('Validate patch'), findsNothing);
    expect(find.text('Approve patch'), findsNothing);
  });

  testWidgets('ambiguous proposal cannot be validated or approved', (
    tester,
  ) async {
    final script = _Script()
      ..getPatch = _proposalJson(
        status: 'ambiguous',
        summary: 'two equally plausible repairs',
        files: const [],
      )
      ..getPatchStatus = 200;

    await _pump(tester, _client(script));
    await _settle(tester);

    expect(find.text('Ambiguous'), findsOneWidget);
    expect(
      find.textContaining('not confident enough to propose a'),
      findsOneWidget,
    );
    expect(find.text('Validate patch'), findsNothing);
    expect(find.text('Approve patch'), findsNothing);
  });

  testWidgets('empty proposal shows no file changes', (tester) async {
    final script = _Script()
      ..getPatch = _proposalJson(
        status: 'empty',
        summary: 'no edits',
        files: const [],
      )
      ..getPatchStatus = 200;

    await _pump(tester, _client(script));
    await _settle(tester);

    expect(find.text('Empty proposal'), findsOneWidget);
    expect(find.textContaining('returned no file changes'), findsOneWidget);
    expect(find.text('Validate patch'), findsNothing);
    expect(find.text('Approve patch'), findsNothing);
  });

  testWidgets('invalid proposal shows deterministic errors', (tester) async {
    final script = _Script()
      ..getPatch = _proposalJson(
        status: 'invalid',
        summary: 'schema failed',
        errors: ['old_text does not match the context slice'],
        files: const [],
      )
      ..getPatchStatus = 200;

    await _pump(tester, _client(script));
    await _settle(tester);

    expect(find.text('Invalid proposal'), findsOneWidget);
    expect(
      find.text('old_text does not match the context slice'),
      findsOneWidget,
    );
    expect(find.text('Validate patch'), findsNothing);
    expect(find.text('Approve patch'), findsNothing);
  });

  testWidgets('shows validation loading then a pass with command results', (
    tester,
  ) async {
    final gate = Completer<http.Response>();
    final script = _Script()
      ..getPatch = _proposalJson()
      ..getPatchStatus = 200
      ..validateGate = gate
      ..postValidation = _validationJson();

    await _pump(tester, _client(script));
    await _settle(tester);

    await tester.tap(find.text('Validate patch'));
    await tester.pump();

    expect(find.text('Validating'), findsOneWidget);
    expect(find.text('Patch applied — running'), findsOneWidget);
    expect(find.text('flutter pub get'), findsOneWidget);
    expect(find.text('flutter analyze'), findsOneWidget);
    expect(find.text('flutter test'), findsOneWidget);
    expect(find.text('Approve patch'), findsNothing);
    expect(find.text('Validate patch'), findsNothing);

    gate.complete(_json(_validationJson(), 200));
    await _settle(tester);

    expect(find.text('Validation passed'), findsOneWidget);
    expect(find.text('Patch applied'), findsOneWidget);
    expect(find.text('flutter pub get'), findsOneWidget);
    expect(find.text('flutter analyze'), findsOneWidget);
    expect(find.text('flutter test'), findsOneWidget);
    expect(find.text('exit 0'), findsNWidgets(3));
    expect(find.text('Approve patch'), findsOneWidget);
    expect(find.text('Create draft PR'), findsNothing);
  });

  testWidgets('validation failure keeps the patch visible', (tester) async {
    final script = _Script()
      ..getPatch = _proposalJson()
      ..getPatchStatus = 200
      ..postValidation = _validationJson(
        status: 'validation_failed',
        passed: false,
        errors: ['flutter analyze reported 2 issues'],
        commands: [
          {
            'name': 'pub_get',
            'argv': ['flutter', 'pub', 'get'],
            'exit_code': 0,
            'timed_out': false,
            'stdout': '',
            'stderr': '',
            'duration_ms': 10,
          },
          {
            'name': 'analyze',
            'argv': ['flutter', 'analyze'],
            'exit_code': 1,
            'timed_out': false,
            'stdout': '',
            'stderr': 'error • unused import',
            'duration_ms': 20,
          },
        ],
      );

    await _pump(tester, _client(script));
    await _settle(tester);

    await tester.tap(find.text('Validate patch'));
    await _settle(tester);

    expect(script.validateCalls, 1);
    expect(find.text('emit loaded state after refresh'), findsOneWidget);
    expect(find.text('lib/bloc/task_bloc.dart'), findsOneWidget);
    expect(find.textContaining('missing emit'), findsOneWidget);
    expect(find.text('Validation failed'), findsOneWidget);
    expect(find.text('Patch applied'), findsOneWidget);
    expect(find.text('flutter analyze reported 2 issues'), findsOneWidget);
    expect(find.text('exit 1'), findsOneWidget);
    expect(find.text('Approve patch'), findsNothing);
  });

  testWidgets('unavailable validation does not unlock approval', (
    tester,
  ) async {
    final script = _Script()
      ..getPatch = _proposalJson()
      ..getPatchStatus = 200
      ..postValidation = _validationJson(
        status: 'passed',
        passed: true,
        runnable: false,
        unavailable: 'missing pubspec.yaml',
        commands: const [],
        warnings: const ['no validation commands configured'],
      );

    await _pump(tester, _client(script));
    await _settle(tester);
    await tester.tap(find.text('Validate patch'));
    await _settle(tester);

    expect(find.text('Validation unavailable'), findsOneWidget);
    expect(find.textContaining('missing pubspec.yaml'), findsOneWidget);
    expect(find.text('Approve patch'), findsNothing);
  });

  testWidgets('approval calls the API and only then allows Create draft PR', (
    tester,
  ) async {
    final script = _Script()
      ..getPatch = _proposalJson()
      ..getPatchStatus = 200
      ..postValidation = _validationJson();

    await _pump(tester, _client(script));
    await _settle(tester);

    expect(find.text('Approve patch'), findsNothing);
    expect(find.text('Create draft PR'), findsNothing);

    await tester.tap(find.text('Validate patch'));
    await _settle(tester);

    expect(find.text('Approve patch'), findsOneWidget);
    expect(find.text('Create draft PR'), findsNothing);

    await tester.ensureVisible(find.text('Approve patch'));
    await tester.tap(find.text('Approve patch'));
    await _settle(tester);

    expect(script.approveCalls, 1);
    expect(find.text('Patch approved'), findsOneWidget);
    expect(find.text('Create draft PR'), findsOneWidget);
    expect(
      find.textContaining('Opening a draft pull request is a separate step'),
      findsOneWidget,
    );
  });

  testWidgets('pinned commit is shown in the patch review panel', (
    tester,
  ) async {
    const sha = 'f0bfc5b317f4984dc2c8d253715e9a30c72c0a5c';
    final script = _Script();

    await _pump(tester, _client(script), commitSha: sha);
    await _settle(tester);

    expect(find.textContaining('Patching f0bfc5b317f4'), findsOneWidget);
    expect(find.text('Generate patch'), findsOneWidget);
  });

  testWidgets('clicking a changed file reports its path and line', (
    tester,
  ) async {
    final opened = <String>[];
    final lines = <int?>[];
    final script = _Script()
      ..getPatch = _proposalJson()
      ..getPatchStatus = 200;

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.build(),
        home: Scaffold(
          body: SingleChildScrollView(
            child: PatchPanel(
              api: _client(script),
              analysisId: 'a1',
              onOpenFile: (path, {int? line, String? reason}) {
                opened.add(path);
                lines.add(line);
              },
            ),
          ),
        ),
      ),
    );
    await _settle(tester);

    await tester.tap(find.text('lib/bloc/task_bloc.dart'));
    await tester.pump();

    expect(opened, ['lib/bloc/task_bloc.dart']);
    expect(lines, [2]);
  });

  testWidgets('approval API failure keeps Create draft PR hidden', (
    tester,
  ) async {
    final script = _Script()
      ..getPatch = _proposalJson()
      ..getPatchStatus = 200
      ..postValidation = _validationJson()
      ..postApprovalStatus = 409;

    await _pump(tester, _client(script));
    await _settle(tester);
    await tester.tap(find.text('Validate patch'));
    await _settle(tester);

    await tester.ensureVisible(find.text('Approve patch'));
    await tester.tap(find.text('Approve patch'));
    await _settle(tester);

    expect(script.approveCalls, 1);
    expect(find.text('The patch has not been validated'), findsOneWidget);
    expect(find.text('Create draft PR'), findsNothing);
    expect(find.text('Approve patch'), findsOneWidget);
    expect(find.text('lib/bloc/task_bloc.dart'), findsOneWidget);
  });

  testWidgets('shows delivery progress while the draft PR is created', (
    tester,
  ) async {
    final gate = Completer<http.Response>();
    final script = _Script()
      ..getPatch = _proposalJson()
      ..getPatchStatus = 200
      ..getValidation = _validationJson()
      ..getValidationStatus = 200
      ..getApproval = _approvalJson()
      ..getApprovalStatus = 200
      ..deliverGate = gate;

    await _pump(tester, _client(script));
    await _settle(tester);

    expect(find.text('Create draft PR'), findsOneWidget);

    await tester.ensureVisible(find.text('Create draft PR'));
    await tester.tap(find.text('Create draft PR'));
    await tester.pump();

    expect(find.text('Opening draft PR'), findsOneWidget);
    expect(find.text('Apply patch'), findsOneWidget);
    expect(find.text('Create commit'), findsOneWidget);
    expect(find.text('Push branch'), findsOneWidget);
    expect(find.text('Open pull request'), findsOneWidget);
    expect(find.text('Create draft PR'), findsNothing);
    expect(find.text('lib/bloc/task_bloc.dart'), findsOneWidget);

    gate.complete(_json(_deliveryJson(), 200));
    await _settle(tester);

    expect(find.text('Draft PR opened'), findsOneWidget);
    expect(find.text('https://github.com/owner/repo/pull/12'), findsOneWidget);
  });

  testWidgets(
    'delivery failure at each stage keeps the patch and allows retry',
    (tester) async {
      for (final stage in ['apply', 'commit', 'push', 'pull_request']) {
        final script = _Script()
          ..getPatch = _proposalJson()
          ..getPatchStatus = 200
          ..getValidation = _validationJson()
          ..getValidationStatus = 200
          ..getApproval = _approvalJson()
          ..getApprovalStatus = 200
          ..postDelivery = _deliveryJson(
            status: 'failed',
            stage: stage,
            prNumber: null,
            prUrl: null,
            commitSha: stage == 'apply' ? null : 'c' * 40,
            branch: stage == 'apply'
                ? null
                : 'patchpilot/issue-1/deadbeef-aaaaaaaa',
            errors: ['failed at $stage'],
          );

        await _pump(tester, _client(script));
        await _settle(tester);
        await tester.ensureVisible(find.text('Create draft PR'));
        await tester.tap(find.text('Create draft PR'));
        await _settle(tester);

        expect(find.textContaining('Delivery failed'), findsOneWidget);
        expect(find.textContaining('failed at $stage'), findsOneWidget);
        expect(find.text('emit loaded state after refresh'), findsOneWidget);
        expect(find.text('Retry draft PR'), findsOneWidget);
        expect(
          find.text('https://github.com/owner/repo/pull/12'),
          findsNothing,
        );

        await tester.pumpWidget(const SizedBox.shrink());
      }
    },
  );

  testWidgets('retry after a failed delivery can open the PR', (tester) async {
    final script = _Script()
      ..getPatch = _proposalJson()
      ..getPatchStatus = 200
      ..getValidation = _validationJson()
      ..getValidationStatus = 200
      ..getApproval = _approvalJson()
      ..getApprovalStatus = 200
      ..postDelivery = _deliveryJson(
        status: 'failed',
        stage: 'push',
        prNumber: null,
        prUrl: null,
        errors: ['ref create failed'],
      );

    await _pump(tester, _client(script));
    await _settle(tester);
    await tester.ensureVisible(find.text('Create draft PR'));
    await tester.tap(find.text('Create draft PR'));
    await _settle(tester);

    expect(find.text('Retry draft PR'), findsOneWidget);
    expect(find.text('lib/bloc/task_bloc.dart'), findsOneWidget);

    script.postDelivery = _deliveryJson();
    await tester.ensureVisible(find.text('Retry draft PR'));
    await tester.tap(find.text('Retry draft PR'));
    await _settle(tester);

    expect(script.deliverCalls, 2);
    expect(find.text('Draft PR opened'), findsOneWidget);
    expect(find.text('https://github.com/owner/repo/pull/12'), findsOneWidget);
    expect(find.text('Retry draft PR'), findsNothing);
  });

  testWidgets(
    'cached successful delivery is shown without creating another PR',
    (tester) async {
      final script = _Script()
        ..getPatch = _proposalJson()
        ..getPatchStatus = 200
        ..getValidation = _validationJson()
        ..getValidationStatus = 200
        ..getApproval = _approvalJson()
        ..getApprovalStatus = 200
        ..getDelivery = _deliveryJson()
        ..getDeliveryStatus = 200;

      await _pump(tester, _client(script));
      await _settle(tester);

      expect(script.deliverCalls, 0);
      expect(find.text('Create draft PR'), findsNothing);
      expect(find.text('Draft PR opened'), findsOneWidget);
      expect(
        find.text('https://github.com/owner/repo/pull/12'),
        findsOneWidget,
      );
      expect(
        find.text('patchpilot/issue-3/f0bfc5b317f4-aaaaaaaa'),
        findsOneWidget,
      );
    },
  );

  testWidgets('delivery panel shows the pinned analyzed commit', (
    tester,
  ) async {
    const sha = 'f0bfc5b317f4984dc2c8d253715e9a30c72c0a5c';
    final script = _Script()
      ..getPatch = _proposalJson()
      ..getPatchStatus = 200
      ..getValidation = _validationJson()
      ..getValidationStatus = 200
      ..getApproval = _approvalJson()
      ..getApprovalStatus = 200;

    await _pump(tester, _client(script), commitSha: sha);
    await _settle(tester);

    expect(find.textContaining('Patching f0bfc5b317f4'), findsWidgets);
    expect(find.text('Create draft PR'), findsOneWidget);
  });

  testWidgets('GitHub permission failure keeps the diff and allows retry', (
    tester,
  ) async {
    const detail =
        'The GitHub token cannot create branches, commits, or pull requests '
        'for this repository. Grant Contents and Pull requests write access '
        '(classic `repo`, or `public_repo` for public repositories).';
    final script = _Script()
      ..getPatch = _proposalJson()
      ..getPatchStatus = 200
      ..getValidation = _validationJson()
      ..getValidationStatus = 200
      ..getApproval = _approvalJson()
      ..getApprovalStatus = 200
      ..postDeliveryStatus = 403
      ..postDeliveryDetail = detail;

    await _pump(
      tester,
      _client(script),
      commitSha: 'f0bfc5b317f4984dc2c8d253715e9a30c72c0a5c',
    );
    await _settle(tester);

    script
      ..getDelivery = _deliveryJson(
        status: 'failed',
        stage: 'commit',
        prNumber: null,
        prUrl: null,
        commitSha: null,
        errors: [detail],
      )
      ..getDeliveryStatus = 200;

    await tester.ensureVisible(find.text('Create draft PR'));
    await tester.tap(find.text('Create draft PR'));
    await _settle(tester);

    expect(
      find.textContaining('Delivery failed (Create commit)'),
      findsOneWidget,
    );
    expect(
      find.textContaining('Grant Contents and Pull requests write access'),
      findsOneWidget,
    );
    expect(find.textContaining('Patching f0bfc5b317f4'), findsWidgets);
    expect(find.text('lib/bloc/task_bloc.dart'), findsOneWidget);
    expect(find.text('Retry draft PR'), findsOneWidget);
    expect(find.text('Create draft PR'), findsNothing);
  });

  testWidgets(
    'http delivery failure still loads stored stage and keeps the diff',
    (tester) async {
      final script = _Script()
        ..getPatch = _proposalJson()
        ..getPatchStatus = 200
        ..getValidation = _validationJson()
        ..getValidationStatus = 200
        ..getApproval = _approvalJson()
        ..getApprovalStatus = 200
        ..postDeliveryStatus = 502;

      await _pump(tester, _client(script));
      await _settle(tester);

      script
        ..getDelivery = _deliveryJson(
          status: 'failed',
          stage: 'commit',
          prNumber: null,
          prUrl: null,
          errors: ['GitHub returned 502'],
        )
        ..getDeliveryStatus = 200;

      await tester.ensureVisible(find.text('Create draft PR'));
      await tester.tap(find.text('Create draft PR'));
      await _settle(tester);

      expect(
        find.textContaining('Delivery failed (Create commit)'),
        findsOneWidget,
      );
      expect(find.text('GitHub returned 502'), findsOneWidget);
      expect(find.text('lib/bloc/task_bloc.dart'), findsOneWidget);
      expect(find.text('Retry draft PR'), findsOneWidget);
      expect(find.text('Delivery failed'), findsNothing);
    },
  );
}

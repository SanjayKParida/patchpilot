import 'package:flutter_test/flutter_test.dart';

import 'package:patchpilot_web/models/models.dart';

void main() {
  test('parses a multi-file proposal with warnings and errors', () {
    final proposal = PatchProposal.fromJson(const {
      'status': 'ok',
      'summary': 'fix both files',
      'reasoning': 'two sites',
      'confidence': 0.8,
      'warnings': ['check tests'],
      'errors': ['stale hunk'],
      'files': [
        {
          'path': 'lib/a.dart',
          'language': 'dart',
          'hunks': [
            {
              'start_line': 2,
              'end_line': 2,
              'old_text': 'old',
              'new_text': 'new',
            }
          ],
        },
        {
          'path': 'lib/b.dart',
          'language': 'dart',
          'hunks': [],
        },
      ],
    });

    expect(proposal.isOk, isTrue);
    expect(proposal.canValidate, isTrue);
    expect(proposal.files, hasLength(2));
    expect(proposal.files.first.hunks.single.startLine, 2);
    expect(proposal.warnings, ['check tests']);
    expect(proposal.errors, ['stale hunk']);
    expect(proposal.confidencePercent, '80% confidence');
  });

  test('non-ok proposals cannot be validated', () {
    final proposal = PatchProposal.fromJson(const {
      'status': 'insufficient_context',
      'summary': '',
      'reasoning': '',
      'files': [],
    });

    expect(proposal.canValidate, isFalse);
  });

  test('apply-only pass is unavailable, not success', () {
    final result = PatchValidationResult.fromJson(const {
      'status': 'passed',
      'applied': true,
      'validation_passed': true,
      'runnable': false,
      'unavailable_reason': 'missing pubspec.yaml',
      'commands': [],
      'errors': [],
      'warnings': ['no validation commands configured'],
    });

    expect(result.isPassed, isFalse);
    expect(result.isUnavailable, isTrue);
    expect(result.isFailed, isFalse);
  });

  test('runnable pass is the only approval-ready result', () {
    final result = PatchValidationResult.fromJson(const {
      'status': 'passed',
      'applied': true,
      'validation_passed': true,
      'runnable': true,
      'unavailable_reason': '',
      'commands': [
        {
          'name': 'pub_get',
          'argv': ['flutter', 'pub', 'get'],
          'exit_code': 0,
          'timed_out': false,
          'stdout': '',
          'stderr': '',
          'duration_ms': 12,
        }
      ],
    });

    expect(result.isPassed, isTrue);
    expect(result.commands.single.displayName, 'flutter pub get');
    expect(result.commands.single.passed, isTrue);
  });

  test('pre-existing analyzer infos can pass with a non-zero exit', () {
    final result = PatchValidationResult.fromJson(const {
      'status': 'passed',
      'applied': true,
      'validation_passed': true,
      'runnable': true,
      'unavailable_reason': '',
      'commands': [
        {
          'name': 'analyze',
          'argv': ['flutter', 'analyze'],
          'exit_code': 1,
          'timed_out': false,
          'passed': true,
          'stdout': '24 issues found.',
          'stderr': '',
          'duration_ms': 800,
        }
      ],
    });

    expect(result.isPassed, isTrue);
    expect(result.commands.single.passed, isTrue);
    expect(result.commands.single.exitCode, 1);
  });

  test('maps flutter command names for the review UI', () {
    expect(
      const ValidationCommandResult(name: 'analyze').displayName,
      'flutter analyze',
    );
    expect(
      const ValidationCommandResult(name: 'test').displayName,
      'flutter test',
    );
  });

  test('parses server-side approval', () {
    final approval = PatchApproval.fromJson(const {
      'approved': true,
      'approved_at': '2026-08-30T12:00:00+00:00',
      'commit_sha': 'f0bfc5b317f4984dc2c8d253715e9a30c72c0a5c',
      'analysis_id': 'a1',
    });

    expect(approval.approved, isTrue);
    expect(approval.commitSha, 'f0bfc5b317f4984dc2c8d253715e9a30c72c0a5c');
  });

  test('succeeded delivery requires a PR URL and number', () {
    final delivery = PatchDelivery.fromJson(const {
      'status': 'succeeded',
      'stage': 'pull_request',
      'branch': 'patchpilot/issue-3/f0bfc5b317f4-aaaaaaaa',
      'commit_sha': 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
      'base_commit_sha': 'f0bfc5b317f4984dc2c8d253715e9a30c72c0a5c',
      'pr_number': 12,
      'pr_url': 'https://github.com/owner/repo/pull/12',
      'draft': true,
      'errors': [],
      'warnings': [],
    });

    expect(delivery.isSucceeded, isTrue);
    expect(delivery.isFailed, isFalse);
    expect(delivery.stageLabel, 'Open pull request');
    expect(delivery.draft, isTrue);
  });

  test('failed delivery is not success even with a branch', () {
    final delivery = PatchDelivery.fromJson(const {
      'status': 'failed',
      'stage': 'push',
      'branch': 'patchpilot/issue-3/f0bfc5b317f4-aaaaaaaa',
      'commit_sha': 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
      'pr_number': null,
      'pr_url': null,
      'draft': true,
      'errors': ['create_ref failed'],
    });

    expect(delivery.isSucceeded, isFalse);
    expect(delivery.isFailed, isTrue);
    expect(delivery.stageLabel, 'Push branch');
  });
}

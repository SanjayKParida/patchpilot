import 'package:flutter_test/flutter_test.dart';

import 'package:patchpilot_web/features/repair/patch/widgets/patch_diff.dart';

void main() {
  test('empty hunks produce no lines', () {
    expect(diffHunkTexts('', ''), isEmpty);
  });

  test('identical texts are unchanged surrounding context', () {
    final lines = diffHunkTexts('keep\nalso', 'keep\nalso', startLine: 10);

    expect(lines.map((line) => line.kind), [
      DiffKind.unchanged,
      DiffKind.unchanged,
    ]);
    expect(lines.first.oldLine, 10);
    expect(lines.first.newLine, 10);
    expect(lines.last.oldLine, 11);
  });

  test('replaced middle keeps prefix and suffix', () {
    final lines = diffHunkTexts(
      'before\nold\nafter',
      'before\nnew\nafter',
      startLine: 4,
    );

    expect(lines.map((line) => '${line.kind.name}:${line.text}').toList(), [
      'unchanged:before',
      'removed:old',
      'added:new',
      'unchanged:after',
    ]);
    expect(lines[1].oldLine, 5);
    expect(lines[2].newLine, 5);
  });

  test('pure addition has only added lines', () {
    final lines = diffHunkTexts('', 'added');

    expect(lines.single.kind, DiffKind.added);
    expect(lines.single.text, 'added');
  });

  test('pure removal has only removed lines', () {
    final lines = diffHunkTexts('gone', '');

    expect(lines.single.kind, DiffKind.removed);
    expect(lines.single.text, 'gone');
  });
}

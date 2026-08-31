/// Line-oriented display of one PatchHunk.
///
/// Built from `old_text` / `new_text` only — no extra LLM diff.
/// Shared prefix and suffix lines stay unmarked so the hunk still
/// shows surrounding context when the generator included it.

enum DiffKind { unchanged, added, removed }

class DiffLine {
  final DiffKind kind;
  final String text;
  final int? oldLine;
  final int? newLine;

  const DiffLine({
    required this.kind,
    required this.text,
    this.oldLine,
    this.newLine,
  });
}

List<String> splitHunkLines(String text) {
  if (text.isEmpty) return const [];

  final parts = text.split('\n');
  if (parts.isNotEmpty && parts.last.isEmpty) {
    return parts.sublist(0, parts.length - 1);
  }
  return parts;
}

List<DiffLine> diffHunkTexts(
  String oldText,
  String newText, {
  int startLine = 1,
}) {
  final oldLines = splitHunkLines(oldText);
  final newLines = splitHunkLines(newText);

  var prefix = 0;
  final maxPrefix = oldLines.length < newLines.length
      ? oldLines.length
      : newLines.length;
  while (prefix < maxPrefix && oldLines[prefix] == newLines[prefix]) {
    prefix += 1;
  }

  var suffix = 0;
  final oldRemain = oldLines.length - prefix;
  final newRemain = newLines.length - prefix;
  final maxSuffix = oldRemain < newRemain ? oldRemain : newRemain;
  while (suffix < maxSuffix &&
      oldLines[oldLines.length - 1 - suffix] ==
          newLines[newLines.length - 1 - suffix]) {
    suffix += 1;
  }

  final lines = <DiffLine>[];
  var oldNumber = startLine;
  var newNumber = startLine;

  for (var i = 0; i < prefix; i++) {
    lines.add(
      DiffLine(
        kind: DiffKind.unchanged,
        text: oldLines[i],
        oldLine: oldNumber,
        newLine: newNumber,
      ),
    );
    oldNumber += 1;
    newNumber += 1;
  }

  final oldMidEnd = oldLines.length - suffix;
  for (var i = prefix; i < oldMidEnd; i++) {
    lines.add(
      DiffLine(
        kind: DiffKind.removed,
        text: oldLines[i],
        oldLine: oldNumber,
      ),
    );
    oldNumber += 1;
  }

  final newMidEnd = newLines.length - suffix;
  for (var i = prefix; i < newMidEnd; i++) {
    lines.add(
      DiffLine(
        kind: DiffKind.added,
        text: newLines[i],
        newLine: newNumber,
      ),
    );
    newNumber += 1;
  }

  for (var i = 0; i < suffix; i++) {
    final oldIndex = oldLines.length - suffix + i;
    lines.add(
      DiffLine(
        kind: DiffKind.unchanged,
        text: oldLines[oldIndex],
        oldLine: oldNumber,
        newLine: newNumber,
      ),
    );
    oldNumber += 1;
    newNumber += 1;
  }

  return lines;
}

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/features/repair/code_viewer/widgets/syntax_highlighter.dart';

void main() {
  const baseStyle = TextStyle(
    color: AppTheme.text,
    fontFamily: AppTheme.mono,
  );

  test('maps supported extensions to grammar ids', () {
    expect(SyntaxHighlighter.languageFromPath('lib/app.dart'), 'dart');
    expect(SyntaxHighlighter.languageFromPath('src/main.ts'), 'typescript');
    expect(SyntaxHighlighter.languageFromPath('src/app.tsx'), 'typescript');
    expect(SyntaxHighlighter.languageFromPath('src/index.js'), 'javascript');
    expect(SyntaxHighlighter.languageFromPath('src/icon.jsx'), 'javascript');
    expect(SyntaxHighlighter.languageFromPath('app.py'), 'python');
    expect(SyntaxHighlighter.languageFromPath('README.md'), isNull);
  });

  testWidgets('unsupported language falls back to plain AppTheme text', (
    tester,
  ) async {
    final span = SyntaxHighlighter.highlight(
      source: 'SELECT 1;',
      language: 'sql',
      baseStyle: baseStyle,
    );

    expect(span.text, 'SELECT 1;');
    expect(span.style?.color, AppTheme.text);
    expect(span.style?.fontFamily, AppTheme.mono);
  });

  testWidgets('dart highlighting uses token colors after grammars load', (
    tester,
  ) async {
    await tester.pumpWidget(const SizedBox());

    final ready = await SyntaxHighlighter.ensureInitialized();
    expect(ready, isTrue);

    const source = 'class TaskBloc {}\n';
    final span = SyntaxHighlighter.highlight(
      source: source,
      language: 'dart',
      baseStyle: baseStyle,
    );

    expect(_hasNonDefaultColor(span), isTrue);
    expect(_plainText(span), source);

    final lines = SyntaxHighlighter.highlightLines(
      source: source,
      language: 'dart',
      baseStyle: baseStyle,
    );
    expect(lines, hasLength(2));
    expect(_hasNonDefaultColor(lines[0]), isTrue);
  });
}

bool _hasNonDefaultColor(InlineSpan span) {
  var found = false;

  span.visitChildren((child) {
    if (child is TextSpan) {
      final color = child.style?.color;
      if (color != null && color != AppTheme.text) {
        found = true;
        return false;
      }
    }
    return true;
  });

  return found;
}

String _plainText(InlineSpan span) {
  final buffer = StringBuffer();
  span.visitChildren((child) {
    if (child is TextSpan && child.text != null) {
      buffer.write(child.text);
    }
    return true;
  });
  return buffer.toString();
}

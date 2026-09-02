import 'package:flutter/material.dart';
import 'package:syntax_highlight/syntax_highlight.dart';

import '../../../../core/theme/app_theme.dart';

/// Thin wrapper around `syntax_highlight`'s [Highlighter].
///
/// Loads only Dart, TypeScript, JavaScript, and Python grammars, and
/// returns a [TextSpan] the source viewer can paint. Never uses the
/// package's [CodeEditor]. Failures and unknown languages fall back to
/// plain [AppTheme.mono] text.
class SyntaxHighlighter {
  SyntaxHighlighter._();

  static const _grammars = ['dart', 'typescript', 'javascript', 'python'];

  static const _themeAssetPaths = [
    'packages/syntax_highlight/themes/dark_vs.json',
    'packages/syntax_highlight/themes/dark_plus.json',
  ];

  static const _fallbackStyle = TextStyle(
    color: AppTheme.text,
    fontFamily: AppTheme.mono,
  );

  static Future<bool>? _init;
  static HighlighterTheme? _theme;
  static final Map<String, Highlighter> _highlighters = {};

  /// Whether grammars and the dark theme have loaded successfully.
  static bool get isReady => _theme != null;

  /// Loads the four grammars and the VS Code dark theme assets.
  ///
  /// Safe to call more than once; later calls share the same [Future].
  /// On Flutter Web this hits the asset bundle asynchronously and must
  /// not be assumed to have finished before the first frame.
  static Future<bool> ensureInitialized() {
    return _init ??= _initialize();
  }

  static Future<bool> _initialize() async {
    try {
      await Highlighter.initialize(_grammars);
      _theme = await HighlighterTheme.loadFromAssets(
        _themeAssetPaths,
        _fallbackStyle,
      );
      return true;
    } catch (_) {
      _theme = null;
      return false;
    }
  }

  /// Grammar id for a file path, or `null` if the extension is unknown.
  static String? languageFromPath(String path) {
    final name = path.split('/').last;
    final dot = name.lastIndexOf('.');
    if (dot <= 0 || dot == name.length - 1) return null;

    switch (name.substring(dot + 1).toLowerCase()) {
      case 'dart':
        return 'dart';
      case 'ts':
      case 'tsx':
        return 'typescript';
      case 'js':
      case 'jsx':
        return 'javascript';
      case 'py':
        return 'python';
      default:
        return null;
    }
  }

  /// Highlights [source] in [language], or plain [baseStyle] text.
  static TextSpan highlight({
    required String source,
    String? language,
    required TextStyle baseStyle,
  }) {
    final highlighter = _highlighterFor(language);
    if (highlighter == null) {
      return TextSpan(text: source, style: baseStyle);
    }

    try {
      return TextSpan(
        style: baseStyle,
        children: [highlighter.highlight(source)],
      );
    } catch (_) {
      return TextSpan(text: source, style: baseStyle);
    }
  }

  /// One [TextSpan] per line of [source], matching `source.split('\\n')`.
  ///
  /// Falls back to plain per-line spans if highlighting is unavailable
  /// or the highlighted span cannot be split without losing a line.
  static List<TextSpan> highlightLines({
    required String source,
    String? language,
    required TextStyle baseStyle,
  }) {
    final lines = source.split('\n');
    final fallback = [
      for (final line in lines)
        TextSpan(
          text: line.isEmpty ? ' ' : line,
          style: baseStyle,
        ),
    ];

    if (_highlighterFor(language) == null) return fallback;

    try {
      final highlighted = highlight(
        source: source,
        language: language,
        baseStyle: baseStyle,
      );
      final split = _splitByNewlines(highlighted);
      if (split.length != lines.length) return fallback;

      return [
        for (var i = 0; i < lines.length; i++)
          lines[i].isEmpty
              ? TextSpan(text: ' ', style: baseStyle)
              : TextSpan(style: baseStyle, children: [split[i]]),
      ];
    } catch (_) {
      return fallback;
    }
  }

  static Highlighter? _highlighterFor(String? language) {
    final theme = _theme;
    final grammar = _canonicalLanguage(language);
    if (theme == null || grammar == null) return null;

    try {
      return _highlighters.putIfAbsent(
        grammar,
        () => Highlighter(language: grammar, theme: theme),
      );
    } catch (_) {
      return null;
    }
  }

  static String? _canonicalLanguage(String? language) {
    if (language == null || language.isEmpty) return null;

    final lower = language.toLowerCase();
    if (_grammars.contains(lower)) return lower;

    switch (lower) {
      case 'ts':
      case 'tsx':
        return 'typescript';
      case 'js':
      case 'jsx':
        return 'javascript';
      case 'py':
        return 'python';
      default:
        return languageFromPath(language);
    }
  }

  static List<TextSpan> _splitByNewlines(TextSpan root) {
    final lines = <TextSpan>[];
    var current = <InlineSpan>[];

    void flush() {
      if (current.isEmpty) {
        lines.add(const TextSpan(text: ''));
      } else if (current.length == 1 && current.first is TextSpan) {
        lines.add(current.first as TextSpan);
      } else {
        lines.add(TextSpan(children: List<InlineSpan>.from(current)));
      }
      current = [];
    }

    void visit(TextSpan span) {
      final text = span.text;
      if (text != null && text.isNotEmpty) {
        final parts = text.split('\n');
        for (var i = 0; i < parts.length; i++) {
          if (i > 0) flush();
          if (parts[i].isNotEmpty) {
            current.add(TextSpan(text: parts[i], style: span.style));
          }
        }
      }

      final children = span.children;
      if (children == null) return;

      for (final child in children) {
        if (child is! TextSpan) continue;
        visit(
          TextSpan(
            text: child.text,
            style: span.style?.merge(child.style) ?? child.style,
            children: child.children,
          ),
        );
      }
    }

    visit(root);
    flush();
    return lines;
  }
}

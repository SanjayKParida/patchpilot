import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:syntax_highlight/syntax_highlight.dart';

import '../../../../core/theme/app_theme.dart';

/// Reusable, compact IDE-style source code viewer for PatchPilot.
///
/// Purely presentational: renders [source] with a fixed line-number
/// gutter, a horizontally-scrollable code pane, an optional highlighted
/// diagnostic line, and syntax highlighting via the real `syntax_highlight`
/// package (TextMate/VS Code-style grammars) when [language] is
/// recognized. Holds no knowledge of how the source was loaded, no file
/// model, no navigation, and no business/app state.
///
/// Syntax highlighting uses the package's actual `Highlighter` /
/// `HighlighterTheme` API — see [_SourceCodeViewerState] for exactly
/// which calls are made and why. There is no hand-written tokenizer,
/// regex-based or otherwise, in this file.
class SourceCodeViewer extends StatefulWidget {
  const SourceCodeViewer({
    super.key,
    required this.source,
    this.highlightedLine,
    this.highlightedReason,
    this.startingLineNumber = 1,
    this.fontSize = 12.5,
    this.language,
  });

  /// The full source content to display.
  final String source;

  /// Absolute 1-indexed source line number to highlight, if any. This is
  /// diagnostic-line state, entirely independent of syntax highlighting:
  /// it still applies (gutter marker, bold line number, subtle row wash)
  /// whether or not [language] is set or its grammar has finished
  /// loading.
  final int? highlightedLine;

  /// Kept for API compatibility. Not rendered inline — see the class
  /// doc on the earlier design pass.
  final String? highlightedReason;

  /// The line number the first line of [source] should be labeled with.
  /// Defaults to 1.
  final int startingLineNumber;

  /// Font size for code and line numbers.
  final double fontSize;

  /// Optional language hint for syntax highlighting. Recognized values:
  /// "dart", "typescript" (or "ts"), "javascript" (or "js"), "python"
  /// (or "py") — case-insensitive. Anything else, or omitting this
  /// parameter, renders plain unhighlighted text; existing call sites
  /// that don't pass it are unaffected.
  final String? language;

  @override
  State<SourceCodeViewer> createState() => _SourceCodeViewerState();
}

/// Implementation notes:
///
/// Fixed gutter + independently horizontally-scrollable code pane: two
/// [ListView.builder]s (one passive gutter, one active code pane) kept
/// in lock-step by mirroring the active list's vertical scroll offset
/// onto the passive one. This is unchanged from the prior pass. The
/// widget is [StatefulWidget] for two reasons now: owning/disposing the
/// two [ScrollController]s, and owning the async syntax-highlighting
/// pipeline described below. Neither is business/app state.
///
/// Syntax highlighting, using the real `syntax_highlight` package:
/// 1. `Highlighter.initialize([language])` — must run once per language
///    before any `Highlighter` can be built for it; loads and parses
///    that language's grammar file. Guarded by [_GrammarLoader] so it
///    only ever runs once per language, even across multiple
///    [SourceCodeViewer] instances.
/// 2. `HighlighterTheme.fromConfiguration(jsonConfig, wrapperStyle)` —
///    builds a theme from a small VS Code/TextMate-style theme JSON
///    (scope → foreground/fontStyle rules) plus a base [TextStyle] used
///    as the fallback for any token whose scope isn't explicitly
///    mapped. This is how the approved restrained palette (indigo
///    keywords, muted-teal types, soft-olive strings, warm-gold
///    function calls, dim italic-gray comments, `AppTheme.text` for
///    everything else) is expressed — no custom rendering logic, just
///    theme configuration consumed by the package's real renderer.
/// 3. `Highlighter(language: ..., theme: ...).highlight(source)` —
///    highlights the *entire* source in one call and returns a single
///    [TextSpan] tree (this is also what correctly handles multi-line
///    constructs like block comments, which a per-line approach
///    cannot). [_splitSpansIntoLines] then walks that tree and slices
///    it back into one span list per line, purely by locating `\n`
///    boundaries inside the package's own returned text — it does not
///    re-classify or re-color anything.
class _SourceCodeViewerState extends State<SourceCodeViewer> {
  static const double _lineHeightFactor = 1.5;
  static const double _gutterMarkerWidth = 3;

  late final ScrollController _codeVerticalController;
  late final ScrollController _gutterVerticalController;

  List<List<InlineSpan>>? _highlightedLines;
  Object? _highlightRequestKey;

  @override
  void initState() {
    super.initState();
    _codeVerticalController = ScrollController();
    _gutterVerticalController = ScrollController();
    _codeVerticalController.addListener(_mirrorGutterOffset);
    _requestHighlighting();
  }

  @override
  void didUpdateWidget(covariant SourceCodeViewer oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.source != widget.source ||
        oldWidget.language != widget.language ||
        oldWidget.fontSize != widget.fontSize) {
      _highlightedLines = null;
      _requestHighlighting();
    }
  }

  void _mirrorGutterOffset() {
    if (!_codeVerticalController.hasClients) return;
    if (!_gutterVerticalController.hasClients) return;
    final offset = _codeVerticalController.offset;
    if (_gutterVerticalController.offset != offset) {
      _gutterVerticalController.jumpTo(offset);
    }
  }

  @override
  void dispose() {
    _codeVerticalController.removeListener(_mirrorGutterOffset);
    _codeVerticalController.dispose();
    _gutterVerticalController.dispose();
    super.dispose();
  }

  void _requestHighlighting() {
    final language = _SupportedLanguage.resolve(widget.language);
    if (language == null) return;

    final requestKey = Object();
    _highlightRequestKey = requestKey;

    _GrammarLoader.ensure(language.grammarId).then((_) {
      if (!mounted || _highlightRequestKey != requestKey) return;

      final wrapperStyle = AppTypography.code(
        fontSize: widget.fontSize,
        height: 1.0,
      );
      final theme = HighlighterTheme.fromConfiguration(
        _highlighterThemeConfigJson,
        wrapperStyle,
      );
      final highlighter = Highlighter(
        language: language.grammarId,
        theme: theme,
      );
      final rootSpan = highlighter.highlight(widget.source);
      final lines = _splitSpansIntoLines(rootSpan);

      setState(() {
        _highlightedLines = lines;
      });
    });
  }

  static List<List<InlineSpan>> _splitSpansIntoLines(TextSpan root) {
    final lines = <List<InlineSpan>>[<InlineSpan>[]];

    void visit(InlineSpan span, TextStyle? inherited) {
      if (span is! TextSpan) return;
      final style = inherited != null && span.style != null
          ? inherited.merge(span.style)
          : (span.style ?? inherited);
      final text = span.text;
      if (text != null && text.isNotEmpty) {
        final parts = text.split('\n');
        for (var i = 0; i < parts.length; i++) {
          if (parts[i].isNotEmpty) {
            lines.last.add(TextSpan(text: parts[i], style: style));
          }
          if (i != parts.length - 1) {
            lines.add(<InlineSpan>[]);
          }
        }
      }
      final children = span.children;
      if (children != null) {
        for (final child in children) {
          visit(child, style);
        }
      }
    }

    visit(root, null);
    return lines;
  }

  @override
  Widget build(BuildContext context) {
    final lines = widget.source.split('\n');
    final lineCount = lines.length;
    final lastLineNumber = widget.startingLineNumber + lineCount - 1;
    final gutterDigits = math.max(2, lastLineNumber.toString().length);

    final codeStyle = AppTypography.code(
      fontSize: widget.fontSize,
      height: 1.0,
    );
    final gutterStyle = AppTypography.code(
      fontSize: widget.fontSize,
      color: AppTheme.textMuted,
      height: 1.0,
    );
    final lineHeight = widget.fontSize * _lineHeightFactor;

    final gutterWidth =
        _measureTextWidth('0' * gutterDigits, gutterStyle) +
        AppSpacing.xs +
        AppSpacing.sm +
        _gutterMarkerWidth;

    final highlightedLines = _highlightedLines;
    final requiredCodeWidth = _requiredCodeWidth(lines, codeStyle);

    return Container(
      color: AppTheme.surface,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Fixed gutter — never scrolls horizontally, mirrors the code
          // pane's vertical position.
          SizedBox(
            width: gutterWidth,
            child: ListView.builder(
              controller: _gutterVerticalController,
              physics: const NeverScrollableScrollPhysics(),
              padding: EdgeInsets.zero,
              itemExtent: lineHeight,
              itemCount: lineCount,
              itemBuilder: (context, index) {
                final lineNumber = widget.startingLineNumber + index;
                final isHighlighted = lineNumber == widget.highlightedLine;
                return _GutterCell(
                  lineNumber: lineNumber,
                  isHighlighted: isHighlighted,
                  style: gutterStyle,
                  markerWidth: _gutterMarkerWidth,
                );
              },
            ),
          ),
          Container(width: 1, color: AppTheme.border),
          // Code pane — fills the remaining viewport and scrolls
          // horizontally only when a source line is genuinely wider.
          Expanded(
            child: LayoutBuilder(
              builder: (context, constraints) {
                final availableWidth = constraints.maxWidth.isFinite
                    ? constraints.maxWidth
                    : 0.0;
                final paneWidth = math.max(availableWidth, requiredCodeWidth);
                final paneHeight = constraints.maxHeight.isFinite
                    ? constraints.maxHeight
                    : 0.0;

                return ClipRect(
                  child: SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: SizedBox(
                      width: paneWidth,
                      height: paneHeight,
                      child: ListView.builder(
                        controller: _codeVerticalController,
                        padding: EdgeInsets.zero,
                        itemExtent: lineHeight,
                        itemCount: lineCount,
                        itemBuilder: (context, index) {
                          final lineNumber = widget.startingLineNumber + index;
                          final isHighlighted =
                              lineNumber == widget.highlightedLine;
                          final spans =
                              (highlightedLines != null &&
                                  index < highlightedLines.length)
                              ? highlightedLines[index]
                              : null;
                          return _CodeCell(
                            plainContent: lines[index],
                            highlightedSpans: spans,
                            isHighlighted: isHighlighted,
                            baseStyle: codeStyle,
                          );
                        },
                      ),
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  /// Longest line width plus cell padding. The pane is at least this
  /// wide so long lines can scroll; never uses the window width.
  double _requiredCodeWidth(List<String> lines, TextStyle style) {
    var maxWidth = 0.0;
    for (final line in lines) {
      final width = _measureTextWidth(line.isEmpty ? ' ' : line, style);
      if (width > maxWidth) maxWidth = width;
    }
    return maxWidth + AppSpacing.md * 2;
  }

  static double _measureTextWidth(String text, TextStyle style) {
    final painter = TextPainter(
      text: TextSpan(text: text, style: style),
      textDirection: TextDirection.ltr,
      maxLines: 1,
    )..layout();
    return painter.width;
  }
}

class _GutterCell extends StatelessWidget {
  const _GutterCell({
    required this.lineNumber,
    required this.isHighlighted,
    required this.style,
    required this.markerWidth,
  });

  final int lineNumber;
  final bool isHighlighted;
  final TextStyle style;
  final double markerWidth;

  @override
  Widget build(BuildContext context) {
    return Container(
      alignment: Alignment.centerRight,
      padding: EdgeInsets.only(right: AppSpacing.sm),
      decoration: BoxDecoration(
        color: AppTheme.surfaceAlt,
        border: Border(
          left: BorderSide(
            color: isHighlighted ? AppTheme.accent : Colors.transparent,
            width: markerWidth,
          ),
        ),
      ),
      child: Text(
        '$lineNumber',
        style: isHighlighted
            ? style.copyWith(
                color: AppTheme.accent,
                fontWeight: FontWeight.w600,
              )
            : style,
      ),
    );
  }
}

class _CodeCell extends StatelessWidget {
  const _CodeCell({
    required this.plainContent,
    required this.highlightedSpans,
    required this.isHighlighted,
    required this.baseStyle,
  });

  /// Raw source text for this line — used when syntax highlighting is
  /// unavailable (no/unsupported [SourceCodeViewer.language], or the
  /// grammar hasn't finished loading yet).
  final String plainContent;

  /// Pre-highlighted spans for this line, sliced from the package's
  /// whole-source [Highlighter.highlight] result. Null while loading or
  /// when no language is set.
  final List<InlineSpan>? highlightedSpans;

  final bool isHighlighted;
  final TextStyle baseStyle;

  @override
  Widget build(BuildContext context) {
    final spans = highlightedSpans;
    final content = spans ?? [TextSpan(text: plainContent, style: baseStyle)];

    return Container(
      // Subtle wash only — never a large saturated block. The gutter
      // marker + bold line number carry the rest of the "this is the
      // exact line" signal. Diagnostic highlighting is applied here
      // regardless of whether syntax highlighting is active.
      color: isHighlighted
          ? AppTheme.accent.withValues(alpha: 0.08)
          : Colors.transparent,
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
      alignment: Alignment.centerLeft,
      child: Text.rich(
        TextSpan(style: baseStyle, children: content),
        softWrap: false,
        overflow: TextOverflow.visible,
      ),
    );
  }
}

/// The four languages this viewer is specified to support, mapped to
/// the `syntax_highlight` package's own grammar identifiers (confirmed
/// against the package: css, dart, go, html, java, javascript, json,
/// kotlin, python, rust, serverpod_protocol, sql, swift, typescript,
/// yaml).
enum _SupportedLanguage {
  dart('dart'),
  typescript('typescript'),
  javascript('javascript'),
  python('python');

  const _SupportedLanguage(this.grammarId);

  final String grammarId;

  static _SupportedLanguage? resolve(String? raw) {
    switch (raw?.toLowerCase().trim()) {
      case 'dart':
        return _SupportedLanguage.dart;
      case 'typescript':
      case 'ts':
        return _SupportedLanguage.typescript;
      case 'javascript':
      case 'js':
        return _SupportedLanguage.javascript;
      case 'python':
      case 'py':
        return _SupportedLanguage.python;
      default:
        return null;
    }
  }
}

/// Guards `Highlighter.initialize` so each grammar is loaded at most
/// once, no matter how many [SourceCodeViewer] instances request it.
abstract final class _GrammarLoader {
  static final Set<String> _initialized = {};
  static final Map<String, Future<void>> _pending = {};

  static Future<void> ensure(String grammarId) {
    if (_initialized.contains(grammarId)) return Future.value();
    return _pending.putIfAbsent(grammarId, () async {
      await Highlighter.initialize([grammarId]);
      _initialized.add(grammarId);
    });
  }
}

/// The approved restrained/desaturated palette, expressed as a
/// VS Code/TextMate theme configuration consumed by
/// `HighlighterTheme.fromConfiguration`. Any scope not listed here
/// falls back to the `wrapper` style passed alongside this config
/// (i.e. `AppTheme.text`) — there is no hardcoded "default" foreground
/// baked into this JSON, so ordinary source text always tracks
/// `AppTheme.text` rather than a guessed color.
final String _highlighterThemeConfigJson = jsonEncode({
  'settings': [
    {
      'scope': ['comment', 'comment.line', 'comment.block'],
      'settings': {'foreground': '#5B6470', 'fontStyle': 'italic'},
    },
    {
      'scope': [
        'keyword',
        'keyword.control',
        'keyword.operator',
        'storage.type',
        'storage.modifier',
      ],
      'settings': {'foreground': '#7C93D1'},
    },
    {
      'scope': [
        'string',
        'string.quoted',
        'string.quoted.single',
        'string.quoted.double',
        'string.quoted.triple',
      ],
      'settings': {'foreground': '#9CB46A'},
    },
    {
      'scope': [
        'entity.name.type',
        'support.type',
        'support.class',
        'support.type.property-name',
      ],
      'settings': {'foreground': '#6FB8AD'},
    },
    {
      'scope': ['constant.numeric', 'constant.language', 'variable.language'],
      'settings': {'foreground': '#C9A35A'},
    },
    {
      'scope': ['entity.name.function', 'support.function'],
      'settings': {'foreground': '#E0B880'},
    },
  ],
});

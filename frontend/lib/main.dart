import 'package:flutter/material.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/features/repair/code_viewer/widgets/syntax_highlighter.dart';

import 'app/app.dart';

export 'app/app.dart';
export 'app/shell.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await AppTypography.ensureCodeFont();
  // Warm syntax grammars so the first code/diff view is highlighted.
  await SyntaxHighlighter.ensureInitialized();
  runApp(const PatchPilotApp());
}

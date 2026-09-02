import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:patchpilot_web/models/models.dart';
import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/features/repair/diagnosis/widgets/why_this_file.dart';

/// The claim this widget makes is "here is why the ranking put this
/// file here, and you can go check". These tests hold it to that.

RelevantFile _file({
  List<EvidenceItem> evidence = const [],
  List<StructuralEdge> structural = const [],
}) {
  return RelevantFile(
    rank: 1,
    path: 'lib/presentation/pages/car_list_screen.dart',
    totalScore: 4.87,
    signalsMatched: 3,
    evidence: evidence,
    structural: structural,
  );
}

Future<void> _pump(
  WidgetTester tester,
  RelevantFile file, {
  void Function({int? line, String? reason})? onOpen,
}) {
  return tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.build(),
      home: Scaffold(
        body: SingleChildScrollView(
          child: RelevantFileCard(
            file: file,
            totalSignals: 6,
            cited: false,
            onOpen: onOpen ?? ({int? line, String? reason}) {},
          ),
        ),
      ),
    ),
  );
}

void main() {
  testWidgets('shows the file and how many signals it matched', (tester) async {
    await _pump(tester, _file());

    expect(find.text('car_list_screen.dart'), findsOneWidget);
    expect(find.text('lib/presentation/pages'), findsOneWidget);
    expect(find.text('3/6 signals'), findsOneWidget);
  });

  testWidgets('evidence is hidden until asked for', (tester) async {
    await _pump(
      tester,
      _file(
        evidence: const [
          EvidenceItem(
            concept: 'loading',
            kind: 'behavior_flow',
            identifier: 'CarsLoading',
            line: 20,
          ),
        ],
      ),
    );

    expect(find.text('CarsLoading'), findsNothing);

    await tester.tap(find.text('Why this file?'));
    await tester.pumpAndSettle();

    expect(find.text('CarsLoading'), findsOneWidget);
    expect(find.text('L20'), findsOneWidget);
  });

  testWidgets('structural edges are shown with their source', (tester) async {
    await _pump(
      tester,
      _file(
        structural: const [
          StructuralEdge(
            relationship: 'imports',
            source: 'lib/main.dart',
            distance: 1,
          ),
        ],
      ),
    );

    await tester.tap(find.text('Why this file?'));
    await tester.pumpAndSettle();

    expect(find.text('Structural relationships'.toUpperCase()), findsOneWidget);

    // The edge is composed of TextSpans, so the finder has to be told
    // to look inside rich text.
    expect(find.textContaining('imports', findRichText: true), findsOneWidget);
    expect(
      find.textContaining('main.dart', findRichText: true),
      findsOneWidget,
    );
  });

  testWidgets('tapping evidence asks to open that exact line', (tester) async {
    int? openedLine;
    String? openedReason;

    await _pump(
      tester,
      _file(
        evidence: const [
          EvidenceItem(
            concept: 'loading',
            kind: 'behavior_flow',
            identifier: 'CarsLoading',
            line: 20,
          ),
        ],
      ),
      onOpen: ({int? line, String? reason}) {
        openedLine = line;
        openedReason = reason;
      },
    );

    await tester.tap(find.text('Why this file?'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('CarsLoading'));

    expect(openedLine, 20);
    expect(openedReason, 'behavior_flow CarsLoading');
  });

  testWidgets('a file with no evidence cannot be expanded', (tester) async {
    await _pump(tester, _file());

    expect(find.text('No evidence recorded'), findsOneWidget);
    expect(find.text('Why this file?'), findsNothing);
  });
}

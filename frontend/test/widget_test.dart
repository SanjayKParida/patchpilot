import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:patchpilot_web/main.dart';
import 'package:patchpilot_web/widgets/common.dart';

void main() {
  testWidgets('landing screen offers a repository to analyze', (tester) async {
    await tester.pumpWidget(const PatchPilotApp());

    expect(find.text('PatchPilot'), findsOneWidget);
    expect(find.text('Analyze repository'), findsOneWidget);
    expect(find.byType(TextField), findsOneWidget);
  });

  testWidgets('short text does not show a more control', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: SizedBox(
            width: 400,
            child: ExpandableText(text: 'A short issue body.'),
          ),
        ),
      ),
    );

    expect(find.text('Show more'), findsNothing);
  });

  testWidgets('long text collapses then expands', (tester) async {
    final body = List.generate(
      10,
      (i) => 'Line ${i + 1} of a long issue description.',
    ).join('\n');

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SizedBox(
            width: 400,
            child: ExpandableText(text: body, maxLines: 5),
          ),
        ),
      ),
    );

    expect(find.text('Show more'), findsOneWidget);

    await tester.tap(find.text('Show more'));
    await tester.pump();

    expect(find.text('Show less'), findsOneWidget);
    expect(find.text('Show more'), findsNothing);
  });
}

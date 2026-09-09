import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:patchpilot_web/core/widgets/common.dart';
import 'package:patchpilot_web/features/repair/diagnosis/widgets/root_cause_section.dart';
import 'package:patchpilot_web/features/repair/review/screens/review_widgets.dart';
import 'package:patchpilot_web/features/repair/shell/repair_section_help.dart';
import 'package:patchpilot_web/models/models.dart';

void main() {
  testWidgets('ROOT CAUSE heading exposes the root-cause info tooltip', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: RootCauseSection(
            diagnosis: const Diagnosis(
              rootCause: 'The bloc never emits.',
              confidence: 0.9,
              explanation: 'The refresh handler stops in TaskLoading.',
              suggestedFix: 'Emit TaskLoaded after the fetch succeeds.',
              citedFiles: ['lib/bloc/task_bloc.dart'],
            ),
            onViewRootCause: (path, line) {},
          ),
        ),
      ),
    );

    expect(find.text('ROOT CAUSE'), findsOneWidget);
    expect(find.byIcon(Icons.info_outline), findsOneWidget);
    expect(find.byTooltip(RepairSectionHelp.rootCause), findsOneWidget);
    expect(
      find.descendant(
        of: find
            .ancestor(of: find.text('ROOT CAUSE'), matching: find.byType(Row))
            .first,
        matching: find.byType(SectionInfoButton),
      ),
      findsOneWidget,
    );
  });

  testWidgets('What changed heading exposes the review summary info tooltip', (
    tester,
  ) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: ReviewSummarySection(
            rootCause: 'The bloc never emits.',
            patchDescription: 'Emit TaskLoaded after the fetch succeeds.',
          ),
        ),
      ),
    );

    expect(find.text('WHAT CHANGED'), findsOneWidget);
    expect(find.byIcon(Icons.info_outline), findsOneWidget);
    expect(find.byTooltip(RepairSectionHelp.whatChanged), findsOneWidget);
    expect(
      find.descendant(
        of: find
            .ancestor(of: find.text('WHAT CHANGED'), matching: find.byType(Row))
            .first,
        matching: find.byType(SectionInfoButton),
      ),
      findsOneWidget,
    );
  });
}

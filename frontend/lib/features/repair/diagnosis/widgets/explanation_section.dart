// explanation_section.dart
import 'package:flutter/material.dart';

import '../../../../core/theme/app_theme.dart';
import '../../../../core/widgets/common.dart';
import '../../../../models/models.dart';
import '../../shell/repair_section_help.dart';

/// Supporting explanation section for PatchPilot's Diagnosis stage.
///
/// Purely presentational: renders [Diagnosis.explanation] under a
/// "EXPLANATION" label, sized and colored to read as concise supporting
/// reasoning rather than a prose card.
///
/// Does not render root cause, relevant files, suggested fix, patch,
/// validation, or related declarations content.
class ExplanationSection extends StatelessWidget {
  const ExplanationSection({super.key, required this.diagnosis});

  /// The diagnosis whose explanation is displayed.
  final Diagnosis diagnosis;

  @override
  Widget build(BuildContext context) {
    if (diagnosis.explanation.isEmpty) {
      return const SizedBox.shrink();
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Row(
          children: [
            Text('EXPLANATION', style: AppTypography.sectionLabel),
            SectionInfoButton(message: RepairSectionHelp.explanation),
          ],
        ),
        const SizedBox(height: 12),
        Text(
          diagnosis.explanation,
          style: const TextStyle(
            color: AppTheme.textSecondary,
            fontSize: 13,
            height: 1.6,
          ),
        ),
      ],
    );
  }
}

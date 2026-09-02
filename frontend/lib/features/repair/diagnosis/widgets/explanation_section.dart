import 'package:flutter/material.dart';

import '../../../../core/theme/app_theme.dart';
import '../../../../models/models.dart';

/// Supporting explanation section for PatchPilot's Diagnosis stage.
///
/// Purely presentational: renders [Diagnosis.explanation] under a subtle
/// "EXPLANATION" label. Deliberately less visually prominent than the
/// Root Cause section — smaller label, no accent color, compact spacing.
///
/// Does not render root cause, relevant files, suggested fix, patch,
/// validation, or related declarations content.
class ExplanationSection extends StatelessWidget {
  const ExplanationSection({
    super.key,
    required this.diagnosis,
  });

  /// The diagnosis whose explanation is displayed.
  final Diagnosis diagnosis;

  @override
  Widget build(BuildContext context) {
    if (diagnosis.explanation.isEmpty) {
      return const SizedBox.shrink();
    }

    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.lg,
        vertical: AppSpacing.sm,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'EXPLANATION',
            style: TextStyle(
              color: AppTheme.textMuted,
              fontSize: 10.5,
              fontWeight: FontWeight.w600,
              letterSpacing: 1.0,
            ),
          ),
          SizedBox(height: AppSpacing.xs),
          Text(
            diagnosis.explanation,
            style: TextStyle(
              color: AppTheme.textMuted,
              fontSize: 13,
              height: 1.5,
            ),
          ),
        ],
      ),
    );
  }
}
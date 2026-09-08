// features/repair/context/widgets/context_summary_bar.dart
//
// INTEGRATION POINT: imports the existing production AppTheme for colors.
// Adjust the import path below if it differs in the real repo.

import 'package:flutter/material.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../models/context_package.dart';

class ContextSummaryBar extends StatelessWidget {
  final ContextPackage package;
  final VoidCallback? onBuildPatch;

  const ContextSummaryBar({
    super.key,
    required this.package,
    this.onBuildPatch,
  });

  @override
  Widget build(BuildContext context) {
    final budget = package.budget;
    final warningLabel = package.hasWarnings
        ? '${package.warnings.length} warning${package.warnings.length == 1 ? '' : 's'}'
        : 'No warnings';

    final tokenLabel = budget.estimatedTokens != null
        ? '~${budget.estimatedTokens} tokens'
        : null;

    final summary = [
      '${package.fileCount} file${package.fileCount == 1 ? '' : 's'}',
      '${budget.usedLines} / ${budget.maxLines} lines',
      ?tokenLabel,
      warningLabel,
    ].join('  ·  ');

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 5),
      child: Wrap(
        alignment: WrapAlignment.spaceBetween,
        crossAxisAlignment: WrapCrossAlignment.center,
        runSpacing: 8,
        children: [
          Text(
            summary,
            style: TextStyle(
              fontSize: 12.5,
              color: package.hasWarnings
                  ? AppTheme.warning
                  : AppTheme.textMuted,
            ),
          ),
          if (onBuildPatch != null) ...[
            const SizedBox(width: 20),
            TextButton(
              onPressed: onBuildPatch,
              style: TextButton.styleFrom(
                foregroundColor: AppTheme.background,
                backgroundColor: AppTheme.accent,
                padding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 8,
                ),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(4),
                ),
              ),
              child: const Text(
                'Build patch →',
                style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

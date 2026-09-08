// features/repair/context/widgets/context_warning_banner.dart
//
// INTEGRATION POINT: imports the existing production AppTheme for colors.
// Adjust the import path below if it differs in the real repo.

import 'package:flutter/material.dart';
import '../../../../core/theme/app_theme.dart';

class ContextWarningBanner extends StatelessWidget {
  final List<String> warnings;

  const ContextWarningBanner({super.key, required this.warnings});

  @override
  Widget build(BuildContext context) {
    if (warnings.isEmpty) return const SizedBox.shrink();

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: AppTheme.warning.withValues(alpha: 0.08),
        border: Border.all(color: AppTheme.warning.withValues(alpha: 0.35)),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (int i = 0; i < warnings.length; i++)
            Padding(
              padding: EdgeInsets.only(top: i == 0 ? 0 : 4),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(Icons.error_outline, size: 13, color: AppTheme.warning),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      warnings[i],
                      style: const TextStyle(fontSize: 12.5, color: AppTheme.text),
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

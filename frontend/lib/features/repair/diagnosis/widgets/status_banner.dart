import 'package:flutter/material.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/core/widgets/common.dart';
import 'package:patchpilot_web/models/models.dart';

class StatusBanner extends StatelessWidget {
  final AnalysisStatus status;
  final String label;
  final VoidCallback? onRetry;
  final VoidCallback? onReanalyze;

  const StatusBanner({
    super.key,
    required this.status,
    required this.label,
    this.onRetry,
    this.onReanalyze,
  });

  @override
  Widget build(BuildContext context) {
    late final Color color;
    late final Widget leading;
    late final String title;

    switch (status) {
      case AnalysisStatus.completed:
        color = AppTheme.success;
        title = 'Analysis complete';
        leading = const Icon(
          Icons.check_circle_outline,
          size: 18,
          color: AppTheme.success,
        );
      case AnalysisStatus.failed:
        color = AppTheme.danger;
        title = 'Analysis failed';
        leading = const Icon(
          Icons.error_outline,
          size: 18,
          color: AppTheme.danger,
        );
      case AnalysisStatus.queued:
      case AnalysisStatus.running:
        color = AppTheme.accent;
        title = 'Analyzing';
        leading = const SizedBox(
          width: 16,
          height: 16,
          child: CircularProgressIndicator(
            strokeWidth: 2,
            color: AppTheme.accent,
          ),
        );
    }

    return Panel(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
      background: color.withValues(alpha: 0.07),
      borderColor: color.withValues(alpha: 0.35),
      child: Row(
        children: [
          leading,
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                    color: color,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  label,
                  style: const TextStyle(
                    fontSize: 13,
                    color: AppTheme.textMuted,
                    height: 1.4,
                  ),
                ),
              ],
            ),
          ),
          if (onRetry != null)
            TextButton(onPressed: onRetry, child: const Text('Retry')),
          if (onReanalyze != null)
            TextButton(onPressed: onReanalyze, child: const Text('Re-analyze')),
        ],
      ),
    );
  }
}

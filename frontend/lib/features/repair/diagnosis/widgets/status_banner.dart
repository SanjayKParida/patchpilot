// status_banner.dart
import 'package:flutter/material.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/core/widgets/motion.dart';
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
          size: 16,
          color: AppTheme.success,
        );
      case AnalysisStatus.failed:
        color = AppTheme.danger;
        title = 'Analysis failed';
        leading = const Icon(
          Icons.error_outline,
          size: 16,
          color: AppTheme.danger,
        );
      case AnalysisStatus.queued:
      case AnalysisStatus.running:
        color = AppTheme.accent;
        title = 'Analyzing';
        leading = const AppSpinner(size: 14);
    }

    return DecoratedBox(
      decoration: BoxDecoration(
        border: Border(
          left: BorderSide(color: color.withValues(alpha: 0.8), width: 2),
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 4, 0, 4),
        child: Row(
          children: [
            leading,
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      color: color,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    label,
                    style: const TextStyle(
                      fontSize: 12.5,
                      color: AppTheme.textMuted,
                      height: 1.4,
                    ),
                  ),
                ],
              ),
            ),
            if (onRetry != null) _InlineAction(label: 'Retry', onTap: onRetry!),
            if (onReanalyze != null)
              _InlineAction(label: 'Re-analyze', onTap: onReanalyze!),
          ],
        ),
      ),
    );
  }
}

/// A plain accent-colored text action — same treatment as the other
/// text links on this screen (View root cause, Show more), so status
/// actions don't read as a different, more "SaaS" affordance.
class _InlineAction extends StatelessWidget {
  const _InlineAction({required this.label, required this.onTap});

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return TextButton(
      onPressed: onTap,
      style: TextButton.styleFrom(
        foregroundColor: AppTheme.accent,
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        minimumSize: Size.zero,
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
      ),
      child: Text(
        label,
        style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w500),
      ),
    );
  }
}

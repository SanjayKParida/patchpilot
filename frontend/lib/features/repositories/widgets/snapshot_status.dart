import 'package:flutter/material.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';

/// Compact, single-line repository/snapshot readiness metadata.
/// Same inputs, same status semantics — quieter presentation only.
class SnapshotStatus extends StatelessWidget {
  final String status;
  final String? sha;
  final int fileCount;
  final String? error;
  final int percent;

  const SnapshotStatus({
    super.key,
    required this.status,
    required this.fileCount,
    required this.percent,
    this.sha,
    this.error,
  });

  @override
  Widget build(BuildContext context) {
    late final Color dotColor;
    late final String label;

    if (status == 'ready') {
      dotColor = AppTheme.success;
      final shortSha = (sha ?? '').isEmpty
          ? ''
          : (sha!.length >= 7 ? sha!.substring(0, 7) : sha!);
      label = shortSha.isEmpty
          ? 'Repository ready'
          : 'Repository ready at $shortSha · $fileCount files';
    } else if (status == 'failed') {
      dotColor = AppTheme.danger;
      label = error == null || error!.isEmpty
          ? 'Could not prepare the repository'
          : 'Could not prepare the repository: $error';
    } else {
      dotColor = AppTheme.textMuted;
      final clamped = percent.clamp(0, 100);
      label = clamped > 0
          ? 'Preparing repository… $clamped%'
          : 'Preparing repository…';
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Container(
              width: 7,
              height: 7,
              decoration: BoxDecoration(
                color: dotColor,
                shape: BoxShape.circle,
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                label,
                maxLines: status == 'failed' ? 2 : 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: 12.5,
                  color: status == 'failed'
                      ? AppTheme.danger
                      : AppTheme.textMuted,
                ),
              ),
            ),
          ],
        ),
        if (status == 'preparing') ...[
          const SizedBox(height: 6),
          ClipRRect(
            borderRadius: BorderRadius.circular(2),
            child: LinearProgressIndicator(
              value: percent <= 0 ? null : (percent.clamp(0, 100) / 100),
              minHeight: 3,
              color: AppTheme.accent,
              backgroundColor: AppTheme.border,
            ),
          ),
        ],
      ],
    );
  }
}

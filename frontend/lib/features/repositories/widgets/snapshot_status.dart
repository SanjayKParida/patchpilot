import 'package:flutter/material.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';

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
    late final IconData icon;
    late final Color color;
    late final String label;

    if (status == 'ready') {
      icon = Icons.check_circle_outline;
      color = AppTheme.success;
      final shortSha = (sha ?? '').isEmpty
          ? ''
          : (sha!.length >= 7 ? sha!.substring(0, 7) : sha!);
      label = shortSha.isEmpty
          ? 'Repository ready'
          : 'Repository ready at $shortSha · $fileCount files';
    } else if (status == 'failed') {
      icon = Icons.error_outline;
      color = AppTheme.danger;
      label = error == null || error!.isEmpty
          ? 'Could not prepare the repository'
          : 'Could not prepare the repository: $error';
    } else {
      icon = Icons.hourglass_empty;
      color = AppTheme.textMuted;
      final clamped = percent.clamp(0, 100);
      label = clamped > 0
          ? 'Preparing repository… $clamped%'
          : 'Preparing repository…';
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Icon(icon, size: 16, color: color),
            const SizedBox(width: 8),
            Expanded(
              child: Text(label, style: TextStyle(fontSize: 13, color: color)),
            ),
          ],
        ),
        if (status == 'preparing') ...[
          const SizedBox(height: 8),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: percent <= 0 ? null : (percent.clamp(0, 100) / 100),
              minHeight: 6,
              color: AppTheme.accent,
              backgroundColor: AppTheme.border,
            ),
          ),
        ],
      ],
    );
  }
}

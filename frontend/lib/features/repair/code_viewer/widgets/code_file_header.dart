import 'package:flutter/material.dart';

import '../../../../core/theme/app_theme.dart';

/// Compact header for PatchPilot's source-code viewer.
///
/// Purely presentational and stateless: renders a file name, its
/// directory/path, a fixed "Read-only" indicator (this viewer never
/// supports editing, so the indicator is not a caller-configurable
/// flag), and optional language and reason/evidence labels. Holds no
/// knowledge of how the file was loaded, no scrolling logic, and
/// performs no navigation — back navigation stays the surrounding
/// screen's responsibility.
///
/// Visual priority, strongest to weakest:
/// 1. [fileName]
/// 2. [directoryPath]
/// 3. the read-only indicator
/// 4. [reason] (when supplied)
/// 5. [language] (when supplied)
class CodeFileHeader extends StatelessWidget {
  const CodeFileHeader({
    super.key,
    required this.fileName,
    required this.directoryPath,
    this.reason,
    this.language,
  });

  /// The file's display name, e.g. "recurrence_engine.dart". Shown as
  /// the primary element.
  final String fileName;

  /// The file's directory/path, e.g. "lib/scheduler/". Shown as
  /// secondary monospace text under [fileName].
  final String directoryPath;

  /// Optional short reason/evidence label, e.g. "stale across DST".
  /// Shown as a restrained but visually distinct accent-tinted pill.
  final String? reason;

  /// Optional language label, e.g. "Dart". Shown as the quietest,
  /// trailing-most element.
  final String? language;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.sm,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Icon(
            Icons.insert_drive_file_outlined,
            size: 16,
            color: AppTheme.textMuted,
          ),
          SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  fileName,
                  style: TextStyle(
                    color: AppTheme.text,
                    fontSize: 13.5,
                    fontWeight: FontWeight.w600,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
                if (directoryPath.isNotEmpty) ...[
                  SizedBox(height: 1),
                  Text(
                    directoryPath,
                    style: TextStyle(
                      color: AppTheme.textMuted,
                      fontFamily: AppTheme.mono,
                      fontSize: 11.5,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ],
            ),
          ),
          SizedBox(width: AppSpacing.sm),
          const _ReadOnlyIndicator(),
          if (reason != null && reason!.isNotEmpty) ...[
            SizedBox(width: AppSpacing.sm),
            _ReasonPill(reason: reason!),
          ],
          if (language != null && language!.isNotEmpty) ...[
            SizedBox(width: AppSpacing.sm),
            Text(
              language!,
              style: TextStyle(
                color: AppTheme.textMuted,
                fontSize: 11,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _ReadOnlyIndicator extends StatelessWidget {
  const _ReadOnlyIndicator();

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(
          Icons.visibility_outlined,
          size: 13,
          color: AppTheme.textMuted,
        ),
        SizedBox(width: 4),
        Text(
          'Read-only',
          style: TextStyle(
            color: AppTheme.textMuted,
            fontSize: 11.5,
          ),
        ),
      ],
    );
  }
}

class _ReasonPill extends StatelessWidget {
  const _ReasonPill({required this.reason});

  final String reason;

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(maxWidth: 180),
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: AppTheme.accent.withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(AppRadii.sm),
      ),
      child: Text(
        reason,
        style: TextStyle(
          color: AppTheme.accent,
          fontSize: 11,
          fontWeight: FontWeight.w500,
        ),
        overflow: TextOverflow.ellipsis,
      ),
    );
  }
}
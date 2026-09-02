import 'package:flutter/material.dart';

import '../../../../core/theme/app_theme.dart';
import '../../../../models/models.dart';

class RelevantFilesSection extends StatelessWidget {
  const RelevantFilesSection({
    super.key,
    required this.files,
    required this.visibleFiles,
    required this.isExpanded,
    required this.onExpandedChanged,
    required this.onOpen,
    this.citedFilePaths = const <String>{},
    this.totalSignalCount = 0,
  });

  final List<RelevantFile> files;
  final List<RelevantFile> visibleFiles;
  final bool isExpanded;
  final ValueChanged<bool> onExpandedChanged;
  final ValueChanged<RelevantFile> onOpen;
  final Set<String> citedFilePaths;
  final int totalSignalCount;

  @override
  Widget build(BuildContext context) {
    final hiddenCount = files.length - visibleFiles.length;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.lg,
            vertical: AppSpacing.sm,
          ),
          child: Row(
            children: [
              Text(
                'RELEVANT FILES',
                style: TextStyle(
                  color: AppTheme.textMuted,
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 1.0,
                ),
              ),
              const Spacer(),
              Text(
                'ranked by evidence',
                style: TextStyle(
                  color: AppTheme.textMuted,
                  fontSize: 11.5,
                  fontStyle: FontStyle.italic,
                ),
              ),
            ],
          ),
        ),
        ...visibleFiles.map(
          (file) => _RelevantFileRow(
            file: file,
            isCited: citedFilePaths.contains(file.path),
            totalSignalCount: totalSignalCount,
            onTap: () => onOpen(file),
          ),
        ),
        if (hiddenCount > 0)
          _ExpandToggle(
            label: 'Show $hiddenCount more',
            onTap: () => onExpandedChanged(true),
          )
        else if (isExpanded)
          _ExpandToggle(
            label: 'Show less',
            onTap: () => onExpandedChanged(false),
          ),
      ],
    );
  }
}

class _RelevantFileRow extends StatelessWidget {
  const _RelevantFileRow({
    required this.file,
    required this.isCited,
    required this.totalSignalCount,
    required this.onTap,
  });

  final RelevantFile file;
  final bool isCited;
  final int totalSignalCount;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Container(
        decoration: BoxDecoration(
          border: Border(
            left: BorderSide(
              color: isCited ? AppTheme.accent : Colors.transparent,
              width: 2,
            ),
          ),
        ),
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.sm,
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Icon(
              Icons.insert_drive_file_outlined,
              size: 15,
              color: AppTheme.textMuted,
            ),
            SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Flexible(
                        child: Text(
                          file.fileName,
                          style: TextStyle(
                            color: AppTheme.text,
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                          ),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      if (isCited) ...[
                        SizedBox(width: AppSpacing.xs),
                        _CitedBadge(),
                      ],
                    ],
                  ),
                  SizedBox(height: 1),
                  Text(
                    file.directory.isEmpty ? file.path : file.directory,
                    style: TextStyle(
                      color: AppTheme.textMuted,
                      fontFamily: AppTheme.mono,
                      fontSize: 11.5,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
            SizedBox(width: AppSpacing.sm),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(
                  '#${file.rank}',
                  style: TextStyle(
                    color: AppTheme.textMuted,
                    fontSize: 11.5,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                if (totalSignalCount > 0) ...[
                  SizedBox(height: 1),
                  Text(
                    '${file.signalsMatched}/$totalSignalCount signals',
                    style: TextStyle(
                      color: AppTheme.textMuted,
                      fontSize: 11,
                    ),
                  ),
                ],
              ],
            ),
            SizedBox(width: AppSpacing.xs),
            Icon(
              Icons.chevron_right,
              size: 16,
              color: AppTheme.textMuted,
            ),
          ],
        ),
      ),
    );
  }
}

class _CitedBadge extends StatelessWidget {
  const _CitedBadge();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
      decoration: BoxDecoration(
        color: AppTheme.accent.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(AppRadii.sm),
      ),
      child: Text(
        'Cited',
        style: TextStyle(
          color: AppTheme.accent,
          fontSize: 10,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}

class _ExpandToggle extends StatelessWidget {
  const _ExpandToggle({required this.label, required this.onTap});

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.sm,
        ),
        child: Text(
          label,
          style: TextStyle(
            color: AppTheme.accent,
            fontSize: 12,
            fontWeight: FontWeight.w500,
          ),
        ),
      ),
    );
  }
}
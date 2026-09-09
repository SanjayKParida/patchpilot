// relevant_files_section.dart
import 'package:flutter/material.dart';

import '../../../../core/theme/app_theme.dart';
import '../../../../core/widgets/common.dart';
import '../../../../models/models.dart';
import '../../shell/repair_section_help.dart';

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
        Row(
          children: [
            Text('RELEVANT FILES', style: AppTypography.sectionLabel),
            const SectionInfoButton(message: RepairSectionHelp.relevantFiles),
            const Spacer(),
            Text('${files.length}', style: AppTypography.caption),
          ],
        ),
        const SizedBox(height: 8),
        ...visibleFiles.asMap().entries.expand((entry) {
          final index = entry.key;
          final file = entry.value;
          return [
            if (index > 0)
              Divider(
                height: 1,
                color: AppTheme.border.withValues(alpha: 0.45),
              ),
            _RelevantFileRow(
              index: index,
              file: file,
              isCited: citedFilePaths.contains(file.path),
              totalSignalCount: totalSignalCount,
              onTap: () => onOpen(file),
            ),
          ];
        }),
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
    required this.index,
    required this.file,
    required this.isCited,
    required this.totalSignalCount,
    required this.onTap,
  });

  final int index;
  final RelevantFile file;
  final bool isCited;
  final int totalSignalCount;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final rankLabel = (index + 1).toString().padLeft(2, '0');
    final subtitle = file.directory.isEmpty ? file.path : file.directory;

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(3),
      child: DecoratedBox(
        decoration: BoxDecoration(
          border: Border(
            left: BorderSide(
              color: isCited ? AppTheme.accent : Colors.transparent,
              width: 2,
            ),
          ),
        ),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(10, 10, 0, 10),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              SizedBox(
                width: 28,
                child: Text(
                  rankLabel,
                  style: const TextStyle(
                    color: AppTheme.textMuted,
                    fontSize: 11,
                    fontFamily: AppTheme.mono,
                  ),
                ),
              ),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Flexible(
                          child: Text(
                            file.fileName,
                            style: const TextStyle(
                              color: AppTheme.text,
                              fontSize: 12.5,
                              fontFamily: AppTheme.mono,
                              fontWeight: FontWeight.w600,
                            ),
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                        if (isCited) ...[
                          const SizedBox(width: 8),
                          const _CitedTag(),
                        ],
                      ],
                    ),
                    const SizedBox(height: 2),
                    Text(
                      subtitle,
                      style: const TextStyle(
                        color: AppTheme.textMuted,
                        fontFamily: AppTheme.mono,
                        fontSize: 11.5,
                      ),
                      overflow: TextOverflow.ellipsis,
                    ),
                    if (totalSignalCount > 0) ...[
                      const SizedBox(height: 2),
                      Text(
                        '${file.signalsMatched}/$totalSignalCount signals',
                        style: const TextStyle(
                          color: AppTheme.textMuted,
                          fontSize: 11,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              const SizedBox(width: 12),
              Text(
                '#${file.rank}',
                style: const TextStyle(
                  color: AppTheme.textMuted,
                  fontSize: 11,
                  fontFamily: AppTheme.mono,
                ),
              ),
              const SizedBox(width: 4),
              const Icon(
                Icons.chevron_right,
                size: 16,
                color: AppTheme.textMuted,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// A quiet inline marker rather than a filled badge — the file's name
/// already carries the weight; this just adds context.
class _CitedTag extends StatelessWidget {
  const _CitedTag();

  @override
  Widget build(BuildContext context) {
    return const Text(
      'CITED',
      style: TextStyle(
        color: AppTheme.accent,
        fontSize: 9.5,
        fontFamily: AppTheme.mono,
        fontWeight: FontWeight.w600,
        letterSpacing: 0.4,
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
        padding: const EdgeInsets.symmetric(vertical: 10),
        child: Text(
          label,
          style: const TextStyle(
            color: AppTheme.accent,
            fontSize: 12,
            fontWeight: FontWeight.w500,
          ),
        ),
      ),
    );
  }
}

// root_cause_section.dart
import 'package:flutter/material.dart';

import '../../../../core/theme/app_theme.dart';
import '../../../../core/widgets/common.dart';
import '../../../../models/models.dart';
import '../../shell/repair_section_help.dart';
import 'symbol_button.dart';

class RootCauseSection extends StatelessWidget {
  const RootCauseSection({
    super.key,
    required this.diagnosis,
    required this.onViewRootCause,
  });

  /// The diagnosis to present.
  final Diagnosis diagnosis;
  final void Function(String path, int? line) onViewRootCause;

  SymbolLocation? get _rootCauseLocation => diagnosis.rootCauseLocation;

  String? get _resolvedPath =>
      _rootCauseLocation?.path ?? diagnosis.affectedFile;

  int? get _resolvedLine => _rootCauseLocation?.line;

  Color _confidenceColor() {
    switch (diagnosis.confidenceBand) {
      case 'high':
        return AppTheme.success;
      case 'medium':
        return AppTheme.warning;
      default:
        return AppTheme.danger;
    }
  }

  @override
  Widget build(BuildContext context) {
    final resolvedPath = _resolvedPath;
    final resolvedLine = _resolvedLine;
    final confidenceColor = _confidenceColor();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Text('ROOT CAUSE', style: AppTypography.sectionLabel),
            const SectionInfoButton(message: RepairSectionHelp.rootCause),
            const Spacer(),
            _ConfidenceBadge(
              label: diagnosis.confidencePercent,
              color: confidenceColor,
            ),
          ],
        ),
        const SizedBox(height: 14),
        // The centerpiece of the whole screen — everything else exists
        // to support or elaborate on this one statement.
        Text(
          diagnosis.rootCause,
          style: const TextStyle(
            color: AppTheme.text,
            fontSize: 20,
            fontWeight: FontWeight.w600,
            height: 1.4,
            letterSpacing: -0.3,
          ),
        ),
        if (resolvedPath != null) ...[
          const SizedBox(height: 20),
          _SourceRow(
            path: resolvedPath,
            line: resolvedLine,
            onOpen: () => onViewRootCause(resolvedPath, resolvedLine),
          ),
        ],
        const SizedBox(height: 12),
        Align(
          alignment: Alignment.centerLeft,
          child: TextButton(
            onPressed: resolvedPath == null
                ? null
                : () => onViewRootCause(resolvedPath, resolvedLine),
            style: TextButton.styleFrom(
              foregroundColor: AppTheme.accent,
              disabledForegroundColor: AppTheme.textMuted,
              padding: const EdgeInsets.symmetric(horizontal: 0, vertical: 4),
              minimumSize: Size.zero,
              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
            ),
            child: const Text(
              'View root cause',
              style: TextStyle(fontSize: 12, fontWeight: FontWeight.w500),
            ),
          ),
        ),
        if (diagnosis.locations.isNotEmpty) ...[
          const SizedBox(height: 20),
          _RelatedDeclarations(
            locations: diagnosis.locations,
            onOpen: onViewRootCause,
          ),
        ],
      ],
    );
  }
}

class _ConfidenceBadge extends StatelessWidget {
  const _ConfidenceBadge({required this.label, required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 6,
          height: 6,
          decoration: BoxDecoration(shape: BoxShape.circle, color: color),
        ),
        const SizedBox(width: 6),
        Text(
          label,
          style: const TextStyle(
            color: AppTheme.textMuted,
            fontSize: 11,
            fontWeight: FontWeight.w500,
            fontFamily: AppTheme.mono,
          ),
        ),
      ],
    );
  }
}

/// The defect location, presented like a jump-to-source affordance in
/// an editor rather than a plain line of text or a generic button.
class _SourceRow extends StatelessWidget {
  const _SourceRow({
    required this.path,
    required this.line,
    required this.onOpen,
  });

  final String path;
  final int? line;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    final location = line == null ? path : '$path:$line';

    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        Text('SOURCE', style: AppTypography.sectionLabel),
        const SizedBox(width: 14),
        Expanded(
          child: Align(
            alignment: Alignment.centerLeft,
            child: Material(
              color: Colors.transparent,
              child: InkWell(
                onTap: onOpen,
                borderRadius: BorderRadius.circular(4),
                hoverColor: AppTheme.accent.withValues(alpha: 0.08),
                splashColor: AppTheme.accent.withValues(alpha: 0.12),
                child: Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 2,
                    vertical: 3,
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.code, size: 13, color: AppTheme.accent),
                      const SizedBox(width: 6),
                      Flexible(
                        child: Text(
                          location,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            color: AppTheme.accent,
                            fontSize: 12,
                            fontFamily: AppTheme.mono,
                            height: 1.35,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _RelatedDeclarations extends StatelessWidget {
  const _RelatedDeclarations({required this.locations, required this.onOpen});

  final List<SymbolLocation> locations;
  final void Function(String path, int? line) onOpen;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Text('DECLARATIONS', style: AppTypography.sectionLabel),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Wrap(
            spacing: 8,
            runSpacing: 8,
            children: locations
                .map(
                  (location) => SymbolButton(
                    location: location,
                    onTap: () => onOpen(location.path, location.line),
                  ),
                )
                .toList(),
          ),
        ),
      ],
    );
  }
}

import 'package:flutter/material.dart';

import '../../../../core/theme/app_theme.dart';
import '../../../../models/models.dart';

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

    return Padding(
      padding: EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Text(
                'ROOT CAUSE',
                style: TextStyle(
                  color: AppTheme.textMuted,
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 1.0,
                ),
              ),
              const Spacer(),
              _ConfidenceBadge(
                label: diagnosis.confidencePercent,
                color: confidenceColor,
              ),
            ],
          ),
          SizedBox(height: AppSpacing.sm),
          Text(
            diagnosis.rootCause,
            style: TextStyle(
              color: AppTheme.text,
              fontSize: 18,
              fontWeight: FontWeight.w700,
              height: 1.3,
            ),
          ),
          if (diagnosis.explanation.isNotEmpty) ...[
            SizedBox(height: AppSpacing.sm),
            Text(
              diagnosis.explanation,
              style: TextStyle(
                color: AppTheme.textMuted,
                fontSize: 13.5,
                height: 1.5,
              ),
            ),
          ],
          SizedBox(height: AppSpacing.lg),
          Divider(height: 1, thickness: 1, color: AppTheme.border),
          SizedBox(height: AppSpacing.lg),
          if (resolvedPath != null)
            _ResolvedLocation(
              path: resolvedPath,
              line: resolvedLine,
              accentColor: AppTheme.accent,
            ),
          SizedBox(height: AppSpacing.md),
          _ViewRootCauseButton(
            enabled: resolvedPath != null,
            onPressed: resolvedPath == null
                ? null
                : () => onViewRootCause(resolvedPath, resolvedLine),
          ),
          if (diagnosis.locations.isNotEmpty) ...[
            SizedBox(height: AppSpacing.lg),
            _RelatedDeclarations(locations: diagnosis.locations),
          ],
        ],
      ),
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
        SizedBox(width: AppSpacing.xs),
        Text(
          label,
          style: TextStyle(
            color: AppTheme.textMuted,
            fontSize: 12,
            fontWeight: FontWeight.w500,
          ),
        ),
      ],
    );
  }
}

class _ResolvedLocation extends StatelessWidget {
  const _ResolvedLocation({
    required this.path,
    required this.line,
    required this.accentColor,
  });

  final String path;
  final int? line;
  final Color accentColor;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 2,
          height: 34,
          margin: EdgeInsets.only(right: AppSpacing.sm, top: 2),
          color: accentColor,
        ),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                path,
                style: TextStyle(
                  color: AppTheme.text,
                  fontFamily: AppTheme.mono,
                  fontSize: 12.5,
                ),
                overflow: TextOverflow.ellipsis,
              ),
              if (line != null) ...[
                SizedBox(height: 2),
                Text(
                  'line $line',
                  style: TextStyle(
                    color: AppTheme.textMuted,
                    fontFamily: AppTheme.mono,
                    fontSize: 12,
                  ),
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }
}

class _ViewRootCauseButton extends StatelessWidget {
  const _ViewRootCauseButton({
    required this.enabled,
    required this.onPressed,
  });

  final bool enabled;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    return ElevatedButton(
      onPressed: onPressed,
      style: ElevatedButton.styleFrom(
        backgroundColor: AppTheme.accent,
        foregroundColor: AppTheme.surface,
        disabledBackgroundColor: AppTheme.border,
        disabledForegroundColor: AppTheme.textMuted,
        elevation: 0,
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.sm,
        ),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppRadii.sm),
        ),
        textStyle: const TextStyle(
          fontSize: 12.5,
          fontWeight: FontWeight.w600,
        ),
      ),
      child: const Text('View root cause'),
    );
  }
}

class _RelatedDeclarations extends StatelessWidget {
  const _RelatedDeclarations({required this.locations});

  final List<SymbolLocation> locations;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'RELATED DECLARATIONS',
          style: TextStyle(
            color: AppTheme.textMuted,
            fontSize: 11,
            fontWeight: FontWeight.w600,
            letterSpacing: 1.0,
          ),
        ),
        SizedBox(height: AppSpacing.sm),
        ...locations.map(
          (location) => Padding(
            padding: EdgeInsets.only(bottom: AppSpacing.xs),
            child: RichText(
              overflow: TextOverflow.ellipsis,
              text: TextSpan(
                children: [
                  TextSpan(
                    text: location.symbol,
                    style: TextStyle(
                      color: AppTheme.textMuted,
                      fontFamily: AppTheme.mono,
                      fontSize: 12,
                    ),
                  ),
                  TextSpan(
                    text: ' \u00B7 ${location.label}',
                    style: TextStyle(
                      color: AppTheme.textMuted,
                      fontFamily: AppTheme.mono,
                      fontSize: 12,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }
}
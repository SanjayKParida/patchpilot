import 'package:flutter/material.dart';
import '../../../core/theme/app_theme.dart';

enum RepairStatusTone { neutral, accent, success, warning, danger, purple }

extension _RepairStatusToneColor on RepairStatusTone {
  Color get color {
    switch (this) {
      case RepairStatusTone.neutral:
        return AppTheme.textMuted;
      case RepairStatusTone.accent:
        return AppTheme.accent;
      case RepairStatusTone.success:
        return AppTheme.success;
      case RepairStatusTone.warning:
        return AppTheme.warning;
      case RepairStatusTone.danger:
        return AppTheme.danger;
      case RepairStatusTone.purple:
        return AppTheme.purple;
    }
  }
}

class RepairStatusBar extends StatelessWidget {
  const RepairStatusBar({
    super.key,
    required this.statusLabel,
    this.statusIcon,
    this.tone = RepairStatusTone.neutral,
    this.supportingText,
    this.primaryActionLabel,
    this.onPrimaryAction,
    this.secondaryActionLabel,
    this.onSecondaryAction,
    this.isLoading = false,
    this.height = 52,
  });

  final String statusLabel;
  final IconData? statusIcon;
  final RepairStatusTone tone;
  final String? supportingText;
  final String? primaryActionLabel;
  final VoidCallback? onPrimaryAction;
  final String? secondaryActionLabel;
  final VoidCallback? onSecondaryAction;
  final bool isLoading;
  final double height;

  bool get _hasPrimaryAction =>
      onPrimaryAction != null && primaryActionLabel != null;

  bool get _hasSecondaryAction =>
      onSecondaryAction != null && secondaryActionLabel != null;

  @override
  Widget build(BuildContext context) {
    final toneColor = tone.color;

    return Container(
      height: height,
      color: AppTheme.surface,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Divider(height: 1, thickness: 1, color: AppTheme.border),
          Expanded(
            child: Padding(
              padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
              child: Row(
                children: [
                  Expanded(
                    child: _StatusLabel(
                      label: statusLabel,
                      supportingText: supportingText,
                      icon: statusIcon,
                      tone: toneColor,
                      isLoading: isLoading,
                    ),
                  ),
                  if (_hasSecondaryAction || _hasPrimaryAction)
                    SizedBox(width: AppSpacing.md),
                  if (_hasSecondaryAction)
                    _SecondaryActionButton(
                      label: secondaryActionLabel!,
                      onPressed: isLoading ? null : onSecondaryAction,
                    ),
                  if (_hasSecondaryAction && _hasPrimaryAction)
                    SizedBox(width: AppSpacing.sm),
                  if (_hasPrimaryAction)
                    _PrimaryActionButton(
                      label: primaryActionLabel!,
                      onPressed: isLoading ? null : onPrimaryAction,
                    ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _StatusLabel extends StatelessWidget {
  const _StatusLabel({
    required this.label,
    required this.supportingText,
    required this.icon,
    required this.tone,
    required this.isLoading,
  });

  final String label;
  final String? supportingText;
  final IconData? icon;
  final Color tone;
  final bool isLoading;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (isLoading)
          SizedBox(
            width: 12,
            height: 12,
            child: CircularProgressIndicator(
              strokeWidth: 1.5,
              valueColor: AlwaysStoppedAnimation<Color>(tone),
            ),
          )
        else if (icon != null)
          Icon(icon, size: 14, color: tone),
        if (isLoading || icon != null) SizedBox(width: AppSpacing.sm),
        Flexible(
          child: Text(
            label,
            style: TextStyle(
              color: AppTheme.text,
              fontWeight: FontWeight.w600,
              fontSize: 13,
            ),
            overflow: TextOverflow.ellipsis,
          ),
        ),
        if (supportingText != null) ...[
          Padding(
            padding: EdgeInsets.symmetric(horizontal: AppSpacing.xs),
            child: Text(
              '\u00B7',
              style: TextStyle(color: AppTheme.textMuted, fontSize: 13),
            ),
          ),
          Flexible(
            child: Text(
              supportingText!,
              style: TextStyle(color: AppTheme.textMuted, fontSize: 12.5),
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ],
    );
  }
}

class _PrimaryActionButton extends StatelessWidget {
  const _PrimaryActionButton({required this.label, required this.onPressed});

  final String label;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    return ElevatedButton(
      onPressed: onPressed,
      style: ElevatedButton.styleFrom(
        backgroundColor: AppTheme.accent,
        foregroundColor: AppTheme.surface,
        disabledBackgroundColor: AppTheme.accent.withValues(alpha: 0.4),
        elevation: 0,
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.sm,
        ),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppRadii.sm),
        ),
        textStyle: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600),
      ),
      child: Text(label),
    );
  }
}

class _SecondaryActionButton extends StatelessWidget {
  const _SecondaryActionButton({required this.label, required this.onPressed});

  final String label;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    return OutlinedButton(
      onPressed: onPressed,
      style: OutlinedButton.styleFrom(
        foregroundColor: AppTheme.text,
        disabledForegroundColor: AppTheme.textMuted,
        side: BorderSide(color: AppTheme.border),
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.sm,
        ),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppRadii.sm),
        ),
        textStyle: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w500),
      ),
      child: Text(label),
    );
  }
}

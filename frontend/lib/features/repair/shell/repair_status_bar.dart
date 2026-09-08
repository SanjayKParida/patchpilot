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
    this.height = 32,
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

  bool get _hasActions => _hasPrimaryAction || _hasSecondaryAction;

  @override
  Widget build(BuildContext context) {
    final toneColor = tone.color;
    final hasContent = statusLabel.trim().isNotEmpty || _hasActions;

    if (!hasContent) {
      return SizedBox(height: height);
    }

    return Container(
      height: _hasActions ? 38 : height,
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.shellPadding),
      decoration: BoxDecoration(
        border: Border(top: BorderSide(color: AppTheme.borderSubtle, width: 1)),
      ),
      child: Row(
        children: [
          Container(
            width: 3,
            height: _hasActions ? 22 : 14,
            margin: const EdgeInsets.only(right: 10),
            decoration: BoxDecoration(
              color: toneColor.withValues(alpha: isLoading ? 0.9 : 0.75),
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          Expanded(
            child: _StatusLabel(
              label: statusLabel,
              supportingText: supportingText,
              icon: statusIcon,
              tone: toneColor,
              isLoading: isLoading,
            ),
          ),
          if (_hasSecondaryAction) ...[
            const SizedBox(width: 8),
            _SecondaryActionButton(
              label: secondaryActionLabel!,
              onPressed: isLoading ? null : onSecondaryAction,
            ),
          ],
          if (_hasPrimaryAction) ...[
            const SizedBox(width: 8),
            _PrimaryActionButton(
              label: primaryActionLabel!,
              onPressed: isLoading ? null : onPrimaryAction,
            ),
          ],
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
      children: [
        if (isLoading)
          _PulsingDot(color: tone)
        else if (icon != null)
          Icon(icon, size: 13, color: tone),
        if (isLoading || icon != null) const SizedBox(width: 8),
        Flexible(
          child: Text(
            label,
            style: const TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w600,
              color: AppTheme.textSecondary,
            ),
            overflow: TextOverflow.ellipsis,
          ),
        ),
        if (supportingText != null && supportingText!.trim().isNotEmpty) ...[
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 6),
            child: Text(
              '·',
              style: TextStyle(color: AppTheme.textMuted, fontSize: 12),
            ),
          ),
          Flexible(
            child: Text(
              supportingText!,
              style: AppTypography.caption.copyWith(color: AppTheme.textMuted),
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ],
    );
  }
}

class _PulsingDot extends StatefulWidget {
  const _PulsingDot({required this.color});

  final Color color;

  @override
  State<_PulsingDot> createState() => _PulsingDotState();
}

class _PulsingDotState extends State<_PulsingDot>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 900),
  )..repeat(reverse: true);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: Tween(
        begin: 0.35,
        end: 1.0,
      ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeInOut)),
      child: Container(
        width: 6,
        height: 6,
        decoration: BoxDecoration(color: widget.color, shape: BoxShape.circle),
      ),
    );
  }
}

class _PrimaryActionButton extends StatelessWidget {
  const _PrimaryActionButton({required this.label, required this.onPressed});

  final String label;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    return FilledButton(
      onPressed: onPressed,
      style: FilledButton.styleFrom(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        minimumSize: Size.zero,
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
        textStyle: const TextStyle(fontSize: 11.5, fontWeight: FontWeight.w600),
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
    return FilledButton(
      onPressed: onPressed,
      style: FilledButton.styleFrom(
        backgroundColor: AppTheme.surfaceElevated,
        foregroundColor: AppTheme.textSecondary,
        disabledBackgroundColor: AppTheme.surfaceAlt,
        disabledForegroundColor: AppTheme.textMuted,
        elevation: 0,
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        minimumSize: Size.zero,
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
        textStyle: const TextStyle(fontSize: 11.5, fontWeight: FontWeight.w500),
      ),
      child: Text(label),
    );
  }
}

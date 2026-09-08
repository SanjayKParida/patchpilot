import 'package:flutter/material.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';

enum RepairStageVisualState { completed, active, locked }

class RepairStageIndicator extends StatelessWidget {
  final String label;
  final RepairStageVisualState state;
  final Color stageAccent;

  /// Optional passthrough — tap handling stays in [RepairWorkflow].
  final VoidCallback? onTap;

  const RepairStageIndicator({
    super.key,
    required this.label,
    required this.state,
    required this.stageAccent,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final active = state == RepairStageVisualState.active;
    final completed = state == RepairStageVisualState.completed;

    final content = AnimatedContainer(
      duration: const Duration(milliseconds: 140),
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: active
            ? stageAccent.withValues(alpha: 0.12)
            : Colors.transparent,
        borderRadius: BorderRadius.circular(AppRadii.sm),
        border: active
            ? Border.all(color: stageAccent.withValues(alpha: 0.35))
            : null,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          _Glyph(state: state, accent: stageAccent),
          const SizedBox(width: 6),
          Text(
            label,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: 12,
              fontWeight: active ? FontWeight.w600 : FontWeight.w500,
              color: active
                  ? AppTheme.text
                  : completed
                  ? AppTheme.textSecondary
                  : AppTheme.textMuted,
            ),
          ),
        ],
      ),
    );

    return Semantics(
      label: '$label, ${_semanticStateLabel(state)}',
      button: onTap != null,
      child: onTap == null
          ? content
          : InkWell(
              onTap: onTap,
              borderRadius: BorderRadius.circular(AppRadii.sm),
              child: content,
            ),
    );
  }

  static String _semanticStateLabel(RepairStageVisualState state) {
    switch (state) {
      case RepairStageVisualState.completed:
        return 'completed';
      case RepairStageVisualState.active:
        return 'current stage';
      case RepairStageVisualState.locked:
        return 'locked';
    }
  }
}

class _Glyph extends StatelessWidget {
  final RepairStageVisualState state;
  final Color accent;

  const _Glyph({required this.state, required this.accent});

  @override
  Widget build(BuildContext context) {
    switch (state) {
      case RepairStageVisualState.completed:
        return Icon(Icons.check, size: 12, color: AppTheme.success);
      case RepairStageVisualState.active:
        return Container(
          width: 7,
          height: 7,
          decoration: BoxDecoration(color: accent, shape: BoxShape.circle),
        );
      case RepairStageVisualState.locked:
        return Container(
          width: 7,
          height: 7,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            border: Border.all(color: AppTheme.border, width: 1.2),
          ),
        );
    }
  }
}

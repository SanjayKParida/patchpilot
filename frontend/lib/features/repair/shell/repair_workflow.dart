import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';

/// The ordered stages of the PatchPilot repair workflow.
///
/// This enum exists purely to identify/order stages for display in
/// [RepairWorkflow] — it carries no behavior and makes no assumptions
/// about how a given stage is implemented.
enum RepairStage {
  issue,
  diagnosis,
  context,
  patch,
  validation,
  review,
  pullRequest,
}

extension RepairStageLabel on RepairStage {
  String get label {
    switch (this) {
      case RepairStage.issue:
        return 'Issue';
      case RepairStage.diagnosis:
        return 'Diagnosis';
      case RepairStage.context:
        return 'Context';
      case RepairStage.patch:
        return 'Patch';
      case RepairStage.validation:
        return 'Validation';
      case RepairStage.review:
        return 'Review';
      case RepairStage.pullRequest:
        return 'Pull Request';
    }
  }
}

class RepairWorkflow extends StatelessWidget {
  const RepairWorkflow({
    super.key,
    required this.currentStage,
    this.completedStages = const <RepairStage>{},
    this.onStageSelected,
    this.stages = RepairStage.values,
  });

  final RepairStage currentStage;
  final Set<RepairStage> completedStages;
  final ValueChanged<RepairStage>? onStageSelected;
  final List<RepairStage> stages;

  @override
  Widget build(BuildContext context) {
    return Container(
      color: AppTheme.surface,
      padding: EdgeInsets.symmetric(vertical: AppSpacing.lg),
      child: ListView.builder(
        padding: EdgeInsets.zero,
        itemCount: stages.length,
        itemBuilder: (context, index) {
          final stage = stages[index];
          final isCurrent = stage == currentStage;
          final isCompleted = completedStages.contains(stage);
          final isLast = index == stages.length - 1;

          return _WorkflowStageTile(
            label: stage.label,
            isCurrent: isCurrent,
            isCompleted: isCompleted,
            isLast: isLast,
            onTap: onStageSelected == null
                ? null
                : () => onStageSelected!(stage),
          );
        },
      ),
    );
  }
}

class _WorkflowStageTile extends StatelessWidget {
  const _WorkflowStageTile({
    required this.label,
    required this.isCurrent,
    required this.isCompleted,
    required this.isLast,
    required this.onTap,
  });

  final String label;
  final bool isCurrent;
  final bool isCompleted;
  final bool isLast;
  final VoidCallback? onTap;

  static const double _nodeSize = 16;
  static const double _lineWidth = 1.5;

  @override
  Widget build(BuildContext context) {
    final Color nodeColor;
    final Color labelColor;
    final FontWeight labelWeight;

    if (isCurrent) {
      nodeColor = AppTheme.accent;
      labelColor = AppTheme.text;
      labelWeight = FontWeight.w600;
    } else if (isCompleted) {
      nodeColor = AppTheme.textMuted;
      labelColor = AppTheme.text;
      labelWeight = FontWeight.w400;
    } else {
      nodeColor = AppTheme.border;
      labelColor = AppTheme.textMuted;
      labelWeight = FontWeight.w400;
    }

    final content = Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.sm,
      ),
      child: IntrinsicHeight(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Node + connecting line column.
            SizedBox(
              width: _nodeSize,
              child: Column(
                children: [
                  _StageNode(
                    isCurrent: isCurrent,
                    isCompleted: isCompleted,
                    color: nodeColor,
                  ),
                  if (!isLast)
                    Expanded(
                      child: Container(
                        width: _lineWidth,
                        margin: const EdgeInsets.symmetric(vertical: 2),
                        color: AppTheme.border,
                      ),
                    ),
                ],
              ),
            ),
            SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.only(top: 1),
                child: Text(
                  label,
                  style: TextStyle(
                    color: labelColor,
                    fontWeight: labelWeight,
                    fontSize: 13,
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );

    if (onTap == null) return content;

    return InkWell(onTap: onTap, child: content);
  }
}

class _StageNode extends StatelessWidget {
  const _StageNode({
    required this.isCurrent,
    required this.isCompleted,
    required this.color,
  });

  final bool isCurrent;
  final bool isCompleted;
  final Color color;

  @override
  Widget build(BuildContext context) {
    const size = _WorkflowStageTile._nodeSize;

    if (isCompleted && !isCurrent) {
      return Container(
        width: size,
        height: size,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          border: Border.all(color: color, width: 1.5),
        ),
        child: Icon(Icons.check, size: 10, color: color),
      );
    }

    if (isCurrent) {
      return Container(
        width: size,
        height: size,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: AppTheme.accent,
        ),
        child: Container(
          width: 6,
          height: 6,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: AppTheme.surface,
          ),
        ),
      );
    }

    return Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      child: Container(
        width: 8,
        height: 8,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          border: Border.all(color: color, width: 1.5),
        ),
      ),
    );
  }
}

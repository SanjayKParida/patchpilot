import 'package:flutter/material.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';

import 'widgets/repair_stage_indicator.dart';

/// The ordered stages of the PatchPilot repair workflow.
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

extension RepairStageAccent on RepairStage {
  Color get accent {
    switch (this) {
      case RepairStage.issue:
      case RepairStage.context:
        return AppTheme.textMuted;
      case RepairStage.diagnosis:
        return AppTheme.stageDiagnosis;
      case RepairStage.patch:
        return AppTheme.stagePatch;
      case RepairStage.validation:
        return AppTheme.stageValidation;
      case RepairStage.review:
        return AppTheme.stageReview;
      case RepairStage.pullRequest:
        return AppTheme.stagePullRequest;
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
    return SizedBox(
      height: 36,
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.shellPadding - 4,
        ),
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(
            children: [
              for (int i = 0; i < stages.length; i++) ...[
                RepairStageIndicator(
                  label: stages[i].label,
                  stageAccent: stages[i].accent,
                  state: _visualState(
                    isCurrent: stages[i] == currentStage,
                    isCompleted: completedStages.contains(stages[i]),
                  ),
                  onTap: onStageSelected == null
                      ? null
                      : () => onStageSelected!(stages[i]),
                ),
                if (i != stages.length - 1)
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 6),
                    child: Icon(
                      Icons.chevron_right,
                      size: 12,
                      color: AppTheme.borderSubtle,
                    ),
                  ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  static RepairStageVisualState _visualState({
    required bool isCurrent,
    required bool isCompleted,
  }) {
    if (isCurrent) return RepairStageVisualState.active;
    if (isCompleted) return RepairStageVisualState.completed;
    return RepairStageVisualState.locked;
  }
}

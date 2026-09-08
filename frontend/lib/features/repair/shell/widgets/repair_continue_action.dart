import 'package:flutter/material.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';

/// Floating stage-progression CTA, shown bottom-right when the current
/// stage has successfully completed.
///
/// Visibility and [onContinue] remain wholly owned by the parent
/// ([RepairSession]). This widget only presents the next-step action.
class RepairContinueAction extends StatelessWidget {
  /// Whether the action should currently be shown. The parent is
  /// responsible for this being true only when the current stage has
  /// genuinely, successfully completed.
  final bool visible;

  /// Label of the stage this action advances to, e.g. "Validation".
  final String nextStageLabel;

  /// Invoked when the user taps the action.
  final VoidCallback onContinue;

  /// Accent of the *current* stage — used as a soft colored shadow tint.
  final Color? accentColor;

  const RepairContinueAction({
    super.key,
    required this.visible,
    required this.nextStageLabel,
    required this.onContinue,
    this.accentColor,
  });

  @override
  Widget build(BuildContext context) {
    if (!visible) return const SizedBox.shrink();

    final accent = accentColor ?? AppTheme.accent;
    final label = 'Continue to $nextStageLabel';

    return Semantics(
      button: true,
      label: label,
      child: TweenAnimationBuilder<double>(
        tween: Tween(begin: 0, end: 1),
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeOut,
        builder: (context, t, child) => Opacity(
          opacity: t,
          child: Transform.translate(
            offset: Offset(0, (1 - t) * 10),
            child: child,
          ),
        ),
        child: DecoratedBox(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(28),
            boxShadow: [
              BoxShadow(
                color: accent.withValues(alpha: 0.42),
                blurRadius: 22,
                spreadRadius: 0,
                offset: const Offset(0, 8),
              ),
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.28),
                blurRadius: 10,
                offset: const Offset(0, 3),
              ),
            ],
          ),
          child: Material(
            color: Colors.white,
            elevation: 0,
            borderRadius: BorderRadius.circular(28),
            clipBehavior: Clip.antiAlias,
            child: InkWell(
              onTap: onContinue,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(18, 14, 16, 14),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      label,
                      style: const TextStyle(
                        color: Colors.black,
                        fontSize: 13.5,
                        fontWeight: FontWeight.w600,
                        letterSpacing: -0.1,
                      ),
                    ),
                    const SizedBox(width: 8),
                    const Icon(
                      Icons.arrow_forward,
                      size: 16,
                      color: Colors.black,
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

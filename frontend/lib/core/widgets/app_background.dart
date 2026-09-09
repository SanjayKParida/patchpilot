import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Full-screen dark canvas with a tinted wash.
///
/// Non-stage screens keep the default bluish tint. Repair stages
/// pass [AppTheme.stageAccent] so the canvas matches the yellow rail.
class AppBackground extends StatelessWidget {
  final Widget child;
  final Color accent;

  const AppBackground({
    super.key,
    required this.child,
    this.accent = AppColors.accent,
  });

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        Positioned.fill(
          child: DecoratedBox(
            decoration: BoxDecoration(
              color: AppColors.canvas,
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomRight,
                colors: [
                  Color.lerp(AppColors.canvas, accent, 0.16)!,
                  AppColors.canvas,
                  Color.lerp(AppColors.canvas, accent, 0.22)!,
                ],
                stops: const [0.0, 0.42, 1.0],
              ),
            ),
          ),
        ),
        Positioned.fill(
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: RadialGradient(
                center: const Alignment(0.72, -0.35),
                radius: 1.35,
                colors: [
                  accent.withValues(alpha: 0.28),
                  accent.withValues(alpha: 0.08),
                  Colors.transparent,
                ],
                stops: const [0.0, 0.38, 1.0],
              ),
            ),
          ),
        ),
        child,
      ],
    );
  }
}

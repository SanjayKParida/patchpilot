import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Full-screen dark canvas with a bluish-purple wash.
///
/// Repair stages pass [accent] so the wash follows the workflow
/// without changing the underlying black base.
class AppBackground extends StatelessWidget {
  final Widget child;
  final Color accent;

  const AppBackground({
    super.key,
    required this.child,
    this.accent = AppColors.gradientPurple,
  });

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        Positioned.fill(
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 420),
            curve: Curves.easeOut,
            decoration: BoxDecoration(
              color: AppColors.canvas,
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [
                  AppColors.canvas,
                  Color.lerp(const Color(0xFF0B0A14), accent, 0.34)!,
                  Color.lerp(AppColors.canvas, AppColors.gradientBlue, 0.18)!,
                ],
                stops: const [0.0, 0.52, 1.0],
              ),
            ),
          ),
        ),
        Positioned.fill(
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 420),
            curve: Curves.easeOut,
            decoration: BoxDecoration(
              gradient: RadialGradient(
                center: const Alignment(0.92, -0.82),
                radius: 1.2,
                colors: [
                  accent.withValues(alpha: 0.24),
                  Colors.transparent,
                ],
              ),
            ),
          ),
        ),
        child,
      ],
    );
  }
}

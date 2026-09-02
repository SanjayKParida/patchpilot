import 'package:flutter/material.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';

/// A file path rendered as an affordance rather than as text.
class OpenFileButton extends StatelessWidget {
  final String path;
  final VoidCallback onTap;

  const OpenFileButton({super.key, required this.path, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(6),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
          decoration: BoxDecoration(
            color: AppTheme.background,
            border: Border.all(color: AppTheme.accent.withValues(alpha: 0.4)),
            borderRadius: BorderRadius.circular(6),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.code, size: 13, color: AppTheme.accent),
              const SizedBox(width: 7),
              Text(
                path.split('/').last,
                style: const TextStyle(
                  fontSize: 12,
                  fontFamily: AppTheme.mono,
                  color: AppTheme.accent,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

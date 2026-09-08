// open_file_button.dart
import 'package:flutter/material.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';

/// A file path rendered as an affordance rather than as text — a
/// neutral-bordered code reference, with accent color reserved for
/// the icon and label so it doesn't compete visually with other
/// accent-colored elements on the screen.
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
        borderRadius: BorderRadius.circular(AppRadii.sm),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
          decoration: BoxDecoration(
            border: Border.all(color: AppTheme.border),
            borderRadius: BorderRadius.circular(AppRadii.sm),
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

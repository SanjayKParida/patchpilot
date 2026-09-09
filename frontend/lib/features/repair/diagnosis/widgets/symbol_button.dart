import 'package:flutter/material.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/models/models.dart';

/// A resolved declaration, rendered as somewhere you can go.
class SymbolButton extends StatelessWidget {
  final SymbolLocation location;
  final VoidCallback onTap;

  const SymbolButton({super.key, required this.location, required this.onTap});

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
            border: Border.all(color: AppTheme.accent.withValues(alpha: 0.45)),
            borderRadius: BorderRadius.circular(6),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.my_location, size: 13, color: AppTheme.accent),
              const SizedBox(width: 7),
              Text(
                location.symbol,
                style: const TextStyle(
                  fontSize: 12,
                  fontFamily: AppTheme.mono,
                  color: AppTheme.text,
                ),
              ),
              const SizedBox(width: 8),
              Text(
                location.label,
                style: const TextStyle(
                  fontSize: 11.5,
                  fontFamily: AppTheme.mono,
                  color: AppTheme.textMuted,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

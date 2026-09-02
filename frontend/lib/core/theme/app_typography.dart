import 'package:flutter/material.dart';

import 'app_colors.dart';

/// Type scale used by the current PatchPilot UI.
class AppTypography {
  static const String mono = 'monospace';

  static const TextStyle body = TextStyle(
    fontSize: 15,
    height: 1.7,
    color: AppColors.text,
  );

  static const TextStyle muted = TextStyle(
    fontSize: 13.5,
    height: 1.5,
    color: AppColors.textMuted,
  );

  static const TextStyle sectionLabel = TextStyle(
    fontSize: 11,
    fontWeight: FontWeight.w700,
    letterSpacing: 1.1,
    color: AppColors.textMuted,
  );

  static const TextStyle button = TextStyle(
    fontSize: 15,
    fontWeight: FontWeight.w600,
  );

  static const TextStyle chip = TextStyle(
    fontSize: 12,
    fontWeight: FontWeight.w600,
  );

  static const TextStyle inputHint = TextStyle(color: AppColors.textMuted);
}

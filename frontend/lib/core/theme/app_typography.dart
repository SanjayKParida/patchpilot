import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import 'app_colors.dart';

/// Type scale for the PatchPilot UI.
class AppTypography {
  /// Bundled JetBrains Mono — declared in pubspec `fonts:` and also
  /// available under `google_fonts/` for the google_fonts package.
  static const String mono = 'JetBrains Mono';

  static const TextStyle title = TextStyle(
    fontSize: 15,
    fontWeight: FontWeight.w600,
    height: 1.35,
    color: AppColors.text,
    letterSpacing: -0.15,
  );

  static const TextStyle body = TextStyle(
    fontSize: 14,
    height: 1.55,
    color: AppColors.text,
  );

  static const TextStyle muted = TextStyle(
    fontSize: 13,
    height: 1.5,
    color: AppColors.textMuted,
  );

  static const TextStyle caption = TextStyle(
    fontSize: 12,
    height: 1.4,
    color: AppColors.textSecondary,
  );

  static const TextStyle sectionLabel = TextStyle(
    fontSize: 10.5,
    fontWeight: FontWeight.w600,
    letterSpacing: 0.8,
    color: AppColors.textMuted,
  );

  static const TextStyle button = TextStyle(
    fontSize: 13.5,
    fontWeight: FontWeight.w600,
  );

  static const TextStyle chip = TextStyle(
    fontSize: 11.5,
    fontWeight: FontWeight.w600,
  );

  static const TextStyle inputHint = TextStyle(color: AppColors.textMuted);

  /// JetBrains Mono style for source, diffs, paths, and other code text.
  static TextStyle code({
    double fontSize = 12.5,
    FontWeight? fontWeight,
    FontStyle? fontStyle,
    Color color = AppColors.text,
    double height = 1.55,
    double? letterSpacing,
  }) {
    return TextStyle(
      fontFamily: mono,
      fontSize: fontSize,
      fontWeight: fontWeight,
      fontStyle: fontStyle,
      color: color,
      height: height,
      letterSpacing: letterSpacing,
    );
  }

  /// Warm the google_fonts loader as a secondary path; pubspec fonts are
  /// the primary registration for [mono].
  static Future<void> ensureCodeFont() async {
    GoogleFonts.jetBrainsMono();
    GoogleFonts.jetBrainsMono(fontWeight: FontWeight.w600);
    GoogleFonts.jetBrainsMono(fontStyle: FontStyle.italic);
    await GoogleFonts.pendingFonts();
  }
}

import 'package:flutter/material.dart';

/// Palette for the current PatchPilot UI.
///
/// Kept as named constants so screens and widgets do not invent
/// one-off colours. Appearance is unchanged from the previous
/// [AppTheme] statics.
class AppColors {
  static const Color background = Color(0xFF0D1117);
  static const Color surface = Color(0xFF161B22);
  static const Color surfaceAlt = Color(0xFF1C2128);
  static const Color border = Color(0xFF30363D);
  static const Color accent = Color(0xFF4C8DFF);
  static const Color text = Color(0xFFE6EDF3);
  static const Color textMuted = Color(0xFF8B949E);
  static const Color success = Color(0xFF3FB950);
  static const Color danger = Color(0xFFF85149);
  static const Color warning = Color(0xFFD29922);
  static const Color purple = Color(0xFFA371F7);
}

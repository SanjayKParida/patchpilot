import 'package:flutter/material.dart';

/// A single source of visual truth.
///
/// PatchPilot is a developer tool, so the palette is dark, dense and
/// quiet: the diagnosis should be the only thing competing for
/// attention on the page.
class AppTheme {
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

  static const String mono = 'monospace';

  static const double maxContentWidth = 960;

  static ThemeData build() {
    final base = ThemeData.dark(useMaterial3: true);

    return base.copyWith(
      scaffoldBackgroundColor: background,
      colorScheme: base.colorScheme.copyWith(
        primary: accent,
        surface: surface,
        error: danger,
      ),
      textTheme: base.textTheme.apply(
        bodyColor: text,
        displayColor: text,
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: surfaceAlt,
        hintStyle: const TextStyle(color: textMuted),
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 16,
          vertical: 16,
        ),
        border: _inputBorder(border),
        enabledBorder: _inputBorder(border),
        focusedBorder: _inputBorder(accent),
        errorBorder: _inputBorder(danger),
        focusedErrorBorder: _inputBorder(danger),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: accent,
          foregroundColor: Colors.white,
          padding: const EdgeInsets.symmetric(
            horizontal: 24,
            vertical: 20,
          ),
          textStyle: const TextStyle(
            fontSize: 15,
            fontWeight: FontWeight.w600,
          ),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(8),
          ),
        ),
      ),
    );
  }

  static OutlineInputBorder _inputBorder(Color color) => OutlineInputBorder(
        borderRadius: BorderRadius.circular(8),
        borderSide: BorderSide(color: color),
      );

  /// Colour for a signal chip, by signal type.
  ///
  /// The types are ranked by how diagnostic they are, and the colours
  /// follow that ordering so the eye lands on the symptom first.
  static Color signalColor(String type) {
    switch (type) {
      case 'behavior':
        return danger;
      case 'architecture':
        return purple;
      case 'technology':
        return accent;
      default:
        return textMuted;
    }
  }

  static Color confidenceColor(String confidence) {
    switch (confidence.toLowerCase()) {
      case 'high':
        return success;
      case 'medium':
        return warning;
      default:
        return textMuted;
    }
  }
}

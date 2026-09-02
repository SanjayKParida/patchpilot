import 'package:flutter/material.dart';

import 'app_colors.dart';
import 'app_radii.dart';
import 'app_spacing.dart';
import 'app_typography.dart';

export 'app_colors.dart';
export 'app_radii.dart';
export 'app_spacing.dart';
export 'app_typography.dart';

/// A single source of visual truth.
class AppTheme {
  static const Color background = AppColors.background;
  static const Color surface = AppColors.surface;
  static const Color surfaceAlt = AppColors.surfaceAlt;
  static const Color border = AppColors.border;
  static const Color accent = AppColors.accent;
  static const Color text = AppColors.text;
  static const Color textMuted = AppColors.textMuted;
  static const Color success = AppColors.success;
  static const Color danger = AppColors.danger;
  static const Color warning = AppColors.warning;
  static const Color purple = AppColors.purple;

  static const String mono = AppTypography.mono;

  static const double maxContentWidth = AppSpacing.maxContentWidth;

  static ThemeData build() {
    final base = ThemeData.dark(useMaterial3: true);

    return base.copyWith(
      scaffoldBackgroundColor: background,
      colorScheme: base.colorScheme.copyWith(
        primary: accent,
        surface: surface,
        error: danger,
      ),
      textTheme: base.textTheme.apply(bodyColor: text, displayColor: text),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: surfaceAlt,
        hintStyle: AppTypography.inputHint,
        contentPadding: AppSpacing.inputPadding,
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
          padding: AppSpacing.buttonPadding,
          textStyle: AppTypography.button,
          shape: RoundedRectangleBorder(borderRadius: AppRadii.button),
        ),
      ),
    );
  }

  static OutlineInputBorder _inputBorder(Color color) => OutlineInputBorder(
    borderRadius: AppRadii.input,
    borderSide: BorderSide(color: color),
  );

  /// Colour for a signal chip, by signal type.
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

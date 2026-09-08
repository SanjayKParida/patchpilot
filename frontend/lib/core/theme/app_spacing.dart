import 'package:flutter/material.dart';

/// Spacing for the PatchPilot UI.
class AppSpacing {
  static const double xs = 4;
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 20;
  static const double xxl = 24;
  static const double section = 28;
  static const double page = 32;

  static const double maxContentWidth = 1040;
  static const double shellPadding = 16;

  static const EdgeInsets inputPadding = EdgeInsets.symmetric(
    horizontal: md,
    vertical: md,
  );

  static const EdgeInsets buttonPadding = EdgeInsets.symmetric(
    horizontal: lg,
    vertical: md,
  );

  static const EdgeInsets pagePadding = EdgeInsets.symmetric(
    horizontal: xxl,
    vertical: section,
  );

  static const EdgeInsets panelPadding = EdgeInsets.all(lg);

  static const EdgeInsets chipPadding = EdgeInsets.symmetric(
    horizontal: 8,
    vertical: 4,
  );
}

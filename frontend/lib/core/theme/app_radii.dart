import 'package:flutter/material.dart';

/// Corner radii used by the current PatchPilot UI.
class AppRadii {
  static const double sm = 8;
  static const double md = 10;
  static const double lg = 20;
  static const double pill = 999;

  static BorderRadius get button => BorderRadius.circular(sm);
  static BorderRadius get input => BorderRadius.circular(sm);
  static BorderRadius get panel => BorderRadius.circular(md);
  static BorderRadius get chip => BorderRadius.circular(lg);
}

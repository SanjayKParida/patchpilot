import 'package:flutter/material.dart';

/// Bundled brand images.
class AppAssets {
  static const favicon = 'assets/favicon.png';
}

class BrandImage extends StatelessWidget {
  final String asset;
  final double? height;
  final double? width;
  final String semanticLabel;

  const BrandImage({
    super.key,
    required this.asset,
    this.height,
    this.width,
    this.semanticLabel = 'PatchPilot',
  });

  @override
  Widget build(BuildContext context) {
    return Semantics(
      image: true,
      label: semanticLabel,
      child: Image.asset(
        asset,
        height: height,
        width: width,
        fit: BoxFit.contain,
        filterQuality: FilterQuality.medium,
      ),
    );
  }
}

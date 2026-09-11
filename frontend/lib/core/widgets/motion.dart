import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Sliding highlight over placeholder shapes.
class Shimmer extends StatefulWidget {
  final Widget child;
  final Duration duration;

  const Shimmer({
    super.key,
    required this.child,
    this.duration = const Duration(milliseconds: 1500),
  });

  @override
  State<Shimmer> createState() => _ShimmerState();
}

class _ShimmerState extends State<Shimmer> with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: widget.duration,
  )..repeat();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final highlight = AppTheme.accent.withValues(alpha: 0.42);
    final base = AppTheme.text.withValues(alpha: 0.06);

    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        final t = Curves.easeInOutCubic.transform(_controller.value);
        return ShaderMask(
          blendMode: BlendMode.srcATop,
          shaderCallback: (bounds) {
            return LinearGradient(
              colors: [base, highlight, base],
              stops: const [0.15, 0.45, 0.75],
              transform: _SlideTransform(-1.15 + 2.3 * t),
            ).createShader(bounds);
          },
          child: child,
        );
      },
      child: widget.child,
    );
  }
}

class _SlideTransform extends GradientTransform {
  const _SlideTransform(this.dx);

  final double dx;

  @override
  Matrix4? transform(Rect bounds, {TextDirection? textDirection}) {
    return Matrix4.translationValues(bounds.width * dx, 0, 0);
  }
}

/// Compact activity indicator used in buttons, banners, and the boot screen.
class AppSpinner extends StatelessWidget {
  final double size;
  final double strokeWidth;
  final Color? color;

  const AppSpinner({
    super.key,
    this.size = 18,
    this.strokeWidth = 2,
    this.color,
  });

  @override
  Widget build(BuildContext context) {
    final diameter = size + 2;
    return SizedBox(
      width: diameter,
      height: diameter,
      child: CupertinoActivityIndicator(
        radius: diameter / 2,
        color: color ?? AppTheme.accent,
      ),
    );
  }
}

/// Download / running bar. Determinate values ease to the new percent.
class AppProgressBar extends StatefulWidget {
  final double? value;
  final double height;
  final Color? color;
  final Color? backgroundColor;

  const AppProgressBar({
    super.key,
    this.value,
    this.height = 3,
    this.color,
    this.backgroundColor,
  });

  @override
  State<AppProgressBar> createState() => _AppProgressBarState();
}

class _AppProgressBarState extends State<AppProgressBar> {
  double _shown = 0;

  @override
  Widget build(BuildContext context) {
    final color = widget.color ?? AppTheme.accent;
    final background = widget.backgroundColor ?? AppTheme.border;
    final target = widget.value;

    if (target == null) {
      return _IndeterminateBar(
        height: widget.height,
        color: color,
        background: background,
      );
    }

    final next = target.clamp(0.0, 1.0);
    final start = _shown;
    _shown = next;

    return TweenAnimationBuilder<double>(
      tween: Tween(begin: start, end: next),
      duration: const Duration(milliseconds: 380),
      curve: Curves.easeOutCubic,
      builder: (context, value, _) {
        return ClipRRect(
          borderRadius: BorderRadius.circular(widget.height),
          child: LinearProgressIndicator(
            value: value,
            minHeight: widget.height,
            color: color,
            backgroundColor: background,
          ),
        );
      },
    );
  }
}

class _IndeterminateBar extends StatefulWidget {
  final double height;
  final Color color;
  final Color background;

  const _IndeterminateBar({
    required this.height,
    required this.color,
    required this.background,
  });

  @override
  State<_IndeterminateBar> createState() => _IndeterminateBarState();
}

class _IndeterminateBarState extends State<_IndeterminateBar>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1300),
  )..repeat();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: widget.height,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(widget.height),
        child: AnimatedBuilder(
          animation: _controller,
          builder: (context, _) {
            final t = Curves.easeInOutCubic.transform(_controller.value);
            return CustomPaint(
              painter: _IndeterminatePainter(
                t: t,
                color: widget.color,
                background: widget.background,
              ),
            );
          },
        ),
      ),
    );
  }
}

class _IndeterminatePainter extends CustomPainter {
  final double t;
  final Color color;
  final Color background;

  const _IndeterminatePainter({
    required this.t,
    required this.color,
    required this.background,
  });

  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawRRect(
      RRect.fromRectAndRadius(Offset.zero & size, Radius.circular(size.height)),
      Paint()..color = background,
    );

    final width = size.width * 0.38;
    final x = (size.width + width) * t - width;
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromLTWH(x, 0, width, size.height),
        Radius.circular(size.height),
      ),
      Paint()
        ..shader = LinearGradient(
          colors: [
            color.withValues(alpha: 0),
            color,
            color,
            color.withValues(alpha: 0),
          ],
          stops: const [0, 0.22, 0.78, 1],
        ).createShader(Rect.fromLTWH(x, 0, width, size.height)),
    );
  }

  @override
  bool shouldRepaint(covariant _IndeterminatePainter old) {
    return old.t != t || old.color != color || old.background != background;
  }
}

/// Breathing activity marker for status rows and running states.
class PulseDot extends StatefulWidget {
  final double size;
  final Color? color;

  const PulseDot({super.key, this.size = 7, this.color});

  @override
  State<PulseDot> createState() => _PulseDotState();
}

class _PulseDotState extends State<PulseDot>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1400),
  )..repeat(reverse: true);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final color = widget.color ?? AppTheme.accent;
    final animation = CurvedAnimation(
      parent: _controller,
      curve: Curves.easeInOutCubic,
    );

    return FadeTransition(
      opacity: Tween<double>(begin: 0.35, end: 1).animate(animation),
      child: ScaleTransition(
        scale: Tween<double>(begin: 0.72, end: 1).animate(animation),
        child: Container(
          width: widget.size,
          height: widget.size,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
        ),
      ),
    );
  }
}

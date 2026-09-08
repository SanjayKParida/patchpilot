import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Centres page content and caps its width so long file paths and
/// prose stay readable on a wide monitor.
class PageBody extends StatelessWidget {
  final Widget child;
  final EdgeInsets padding;

  const PageBody({
    super.key,
    required this.child,
    this.padding = AppSpacing.pagePadding,
  });

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: padding,
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: AppTheme.maxContentWidth),
          child: child,
        ),
      ),
    );
  }
}

class Branding extends StatelessWidget {
  final double size;

  const Branding({super.key, this.size = 28});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: size,
          height: size,
          decoration: BoxDecoration(
            color: AppTheme.accent,
            borderRadius: BorderRadius.circular(AppRadii.sm),
          ),
          child: Icon(Icons.radar, size: size * 0.58, color: Colors.white),
        ),
        SizedBox(width: size * 0.38),
        Text(
          'PatchPilot',
          style: TextStyle(
            fontSize: size * 0.62,
            fontWeight: FontWeight.w600,
            letterSpacing: -0.3,
            color: AppTheme.text,
          ),
        ),
      ],
    );
  }
}

/// Elevated surface block. Borders are optional — depth comes from the
/// surface tint rather than a box outline.
class Panel extends StatelessWidget {
  final Widget child;
  final EdgeInsets padding;
  final Color? background;
  final Color? borderColor;
  final bool bordered;

  const Panel({
    super.key,
    required this.child,
    this.padding = AppSpacing.panelPadding,
    this.background,
    this.borderColor,
    this.bordered = false,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: padding,
      decoration: BoxDecoration(
        color: background ?? AppTheme.surfaceElevated,
        borderRadius: AppRadii.panel,
        border: bordered || borderColor != null
            ? Border.all(color: borderColor ?? AppTheme.borderSubtle)
            : null,
      ),
      child: child,
    );
  }
}

class SectionTitle extends StatelessWidget {
  final String title;
  final String? trailing;

  const SectionTitle(this.title, {super.key, this.trailing});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Row(
        children: [
          Flexible(
            child: Text(
              title.toUpperCase(),
              overflow: TextOverflow.ellipsis,
              maxLines: 1,
              style: AppTypography.sectionLabel,
            ),
          ),
          if (trailing != null) ...[
            const SizedBox(width: AppSpacing.sm),
            Flexible(
              child: Text(
                trailing!,
                overflow: TextOverflow.ellipsis,
                maxLines: 1,
                textAlign: TextAlign.right,
                style: AppTypography.caption,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class StatusChip extends StatelessWidget {
  final String label;
  final Color color;
  final IconData? icon;

  const StatusChip({
    super.key,
    required this.label,
    required this.color,
    this.icon,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: AppSpacing.chipPadding,
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: AppRadii.chip,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(icon, size: 12, color: color),
            const SizedBox(width: 5),
          ],
          Text(label, style: AppTypography.chip.copyWith(color: color)),
        ],
      ),
    );
  }
}

class ErrorNotice extends StatelessWidget {
  final String message;
  final VoidCallback? onRetry;
  final String? title;

  const ErrorNotice({
    super.key,
    required this.message,
    this.onRetry,
    this.title,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
      decoration: BoxDecoration(
        color: AppTheme.danger.withValues(alpha: 0.08),
        borderRadius: AppRadii.panel,
        border: Border(
          left: BorderSide(
            color: AppTheme.danger.withValues(alpha: 0.85),
            width: 3,
          ),
        ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.error_outline, color: AppTheme.danger, size: 18),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (title != null) ...[
                  Text(
                    title!,
                    style: const TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      color: AppTheme.danger,
                    ),
                  ),
                  const SizedBox(height: 4),
                ],
                Text(
                  message,
                  style: const TextStyle(
                    color: AppTheme.textSecondary,
                    fontSize: 13,
                    height: 1.45,
                  ),
                ),
              ],
            ),
          ),
          if (onRetry != null) ...[
            const SizedBox(width: AppSpacing.md),
            TextButton(onPressed: onRetry, child: const Text('Retry')),
          ],
        ],
      ),
    );
  }
}

/// Collapses long prose to [maxLines], with a Show more / Show less
/// control only when the text actually overflows.
class ExpandableText extends StatefulWidget {
  final String text;
  final int maxLines;
  final TextStyle? style;

  const ExpandableText({
    super.key,
    required this.text,
    this.maxLines = 5,
    this.style,
  });

  @override
  State<ExpandableText> createState() => _ExpandableTextState();
}

class _ExpandableTextState extends State<ExpandableText> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final style = widget.style ?? DefaultTextStyle.of(context).style;

    return LayoutBuilder(
      builder: (context, constraints) {
        final painter = TextPainter(
          text: TextSpan(text: widget.text, style: style),
          maxLines: widget.maxLines,
          textDirection: Directionality.of(context),
        )..layout(maxWidth: constraints.maxWidth);

        final overflows = painter.didExceedMaxLines;

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              widget.text,
              style: style,
              maxLines: _expanded ? null : widget.maxLines,
              overflow: _expanded
                  ? TextOverflow.visible
                  : TextOverflow.ellipsis,
            ),
            if (overflows)
              ShowMoreLink(
                expanded: _expanded,
                onPressed: () => setState(() => _expanded = !_expanded),
              ),
          ],
        );
      },
    );
  }
}

/// Text-only disclosure used wherever a list or block is truncated.
class ShowMoreLink extends StatelessWidget {
  final bool expanded;
  final VoidCallback onPressed;
  final String? moreLabel;
  final String lessLabel;

  const ShowMoreLink({
    super.key,
    required this.expanded,
    required this.onPressed,
    this.moreLabel,
    this.lessLabel = 'Show less',
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.xs),
      child: TextButton(
        onPressed: onPressed,
        style: TextButton.styleFrom(
          padding: const EdgeInsets.symmetric(horizontal: 0, vertical: 4),
          minimumSize: Size.zero,
          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
          foregroundColor: AppTheme.accent,
        ),
        child: Text(expanded ? lessLabel : (moreLabel ?? 'Show more')),
      ),
    );
  }
}

class EmptyNotice extends StatelessWidget {
  final IconData icon;
  final String message;
  final String? title;

  const EmptyNotice({
    super.key,
    required this.icon,
    required this.message,
    this.title,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(
        vertical: AppSpacing.xxl,
        horizontal: AppSpacing.lg,
      ),
      child: Column(
        children: [
          Icon(icon, size: 28, color: AppTheme.textMuted),
          const SizedBox(height: AppSpacing.sm),
          if (title != null) ...[
            Text(
              title!,
              textAlign: TextAlign.center,
              style: AppTypography.title.copyWith(fontSize: 14),
            ),
            const SizedBox(height: 4),
          ],
          Text(
            message,
            textAlign: TextAlign.center,
            style: AppTypography.muted,
          ),
        ],
      ),
    );
  }
}

// features/repair/context/widgets/context_slice_row.dart
//
// Compact context evidence row. Path is primary; tier + line range are
// secondary metadata. Verbose reason/symbols live in the inspect panel.

import 'package:flutter/material.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../models/context_package.dart';

const double _spaceSm = 8;
const double _spaceMd = 10;

class ContextSliceRow extends StatefulWidget {
  final ContextSlice slice;
  final int displayIndex;
  final VoidCallback onOpenFile;
  final VoidCallback onInspect;

  const ContextSliceRow({
    super.key,
    required this.slice,
    required this.displayIndex,
    required this.onOpenFile,
    required this.onInspect,
  });

  @override
  State<ContextSliceRow> createState() => _ContextSliceRowState();
}

class _ContextSliceRowState extends State<ContextSliceRow> {
  bool _hovered = false;

  Color get _tierColor {
    switch (widget.slice.tier) {
      case ContextTier.t0Defect:
        return AppTheme.danger;
      case ContextTier.t1Supporting:
        return AppTheme.accent;
      case ContextTier.t5Tests:
        return AppTheme.success;
      default:
        return AppTheme.textMuted;
    }
  }

  @override
  Widget build(BuildContext context) {
    final slice = widget.slice;
    final isDefectSite = slice.tier == ContextTier.t0Defect;

    final meta = StringBuffer(slice.tier.code);
    if (slice.hasLineRange) {
      meta.write(' · ${slice.lineRangeLabel}');
    }

    return MouseRegion(
      onEnter: (_) => setState(() => _hovered = true),
      onExit: (_) => setState(() => _hovered = false),
      child: Material(
        color: _hovered ? AppTheme.surfaceAlt : Colors.transparent,
        child: InkWell(
          onTap: widget.onOpenFile,
          child: Container(
            padding: const EdgeInsets.symmetric(
              horizontal: 16,
              vertical: _spaceMd,
            ),
            decoration: const BoxDecoration(
              border: Border(
                bottom: BorderSide(color: AppTheme.borderSubtle, width: 1),
              ),
            ),
            child: Row(
              children: [
                SizedBox(
                  width: 24,
                  child: Text(
                    widget.displayIndex.toString().padLeft(2, '0'),
                    style: TextStyle(
                      fontFamily: AppTheme.mono,
                      fontSize: 11.5,
                      color: isDefectSite ? AppTheme.text : AppTheme.textMuted,
                    ),
                  ),
                ),
                Expanded(
                  child: Row(
                    children: [
                      Flexible(
                        child: Text(
                          slice.filePath,
                          style: TextStyle(
                            fontFamily: AppTheme.mono,
                            fontSize: 12.5,
                            color: AppTheme.text,
                            fontWeight: isDefectSite
                                ? FontWeight.w600
                                : FontWeight.w400,
                          ),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      const SizedBox(width: _spaceSm),
                      Text(
                        meta.toString(),
                        style: TextStyle(
                          fontSize: 11.5,
                          color: _tierColor,
                          fontWeight: isDefectSite
                              ? FontWeight.w600
                              : FontWeight.w400,
                        ),
                      ),
                      if (slice.truncated) ...[
                        const SizedBox(width: _spaceSm),
                        const _StateChip(
                          label: 'truncated',
                          color: AppTheme.warning,
                        ),
                      ],
                      if (slice.omitted) ...[
                        const SizedBox(width: _spaceSm),
                        const _StateChip(
                          label: 'omitted',
                          color: AppTheme.textMuted,
                        ),
                      ],
                    ],
                  ),
                ),
                const SizedBox(width: _spaceSm),
                _InspectButton(onTap: widget.onInspect, visible: _hovered),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _StateChip extends StatelessWidget {
  final String label;
  final Color color;

  const _StateChip({required this.label, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
      decoration: BoxDecoration(
        border: Border.all(color: color.withValues(alpha: 0.5)),
        borderRadius: BorderRadius.circular(3),
      ),
      child: Text(
        label,
        style: TextStyle(fontFamily: AppTheme.mono, fontSize: 10, color: color),
      ),
    );
  }
}

class _InspectButton extends StatelessWidget {
  final VoidCallback onTap;
  final bool visible;

  const _InspectButton({required this.onTap, required this.visible});

  @override
  Widget build(BuildContext context) {
    return AnimatedOpacity(
      opacity: visible ? 1 : 0,
      duration: const Duration(milliseconds: 120),
      child: IgnorePointer(
        ignoring: !visible,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(4),
          child: const Padding(
            padding: EdgeInsets.all(4),
            child: Icon(
              Icons.info_outline,
              size: 14,
              color: AppTheme.textMuted,
            ),
          ),
        ),
      ),
    );
  }
}

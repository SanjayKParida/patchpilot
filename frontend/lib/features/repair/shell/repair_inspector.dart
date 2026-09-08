import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';

class RepairInspector extends StatelessWidget {
  const RepairInspector({
    super.key,
    this.child,
    this.onClose,
    this.title = 'Inspector',
  });

  final Widget? child;
  final VoidCallback? onClose;
  final String title;

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: AppTheme.chrome,
      child: Row(
        children: [
          Container(width: 1, color: AppTheme.borderSubtle),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _InspectorHeader(title: title, onClose: onClose),
                Expanded(
                  child: ColoredBox(
                    color: AppTheme.surface,
                    child: child == null
                        ? const _InspectorEmptyState()
                        : SingleChildScrollView(
                            padding: const EdgeInsets.fromLTRB(14, 10, 14, 14),
                            child: child,
                          ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _InspectorHeader extends StatelessWidget {
  const _InspectorHeader({required this.title, required this.onClose});

  final String title;
  final VoidCallback? onClose;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 40,
      padding: const EdgeInsets.symmetric(horizontal: 12),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: AppTheme.borderSubtle)),
      ),
      child: Row(
        children: [
          const Icon(
            Icons.view_sidebar_outlined,
            size: 14,
            color: AppTheme.textMuted,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              title,
              style: const TextStyle(
                fontFamily: AppTheme.mono,
                fontSize: 12,
                fontWeight: FontWeight.w600,
                color: AppTheme.textSecondary,
              ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
          if (onClose != null)
            IconButton(
              onPressed: onClose,
              tooltip: 'Close inspector',
              icon: const Icon(
                Icons.close,
                size: 16,
                color: AppTheme.textMuted,
              ),
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(minWidth: 28, minHeight: 28),
            ),
        ],
      ),
    );
  }
}

class _InspectorEmptyState extends StatelessWidget {
  const _InspectorEmptyState();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Text(
        'Nothing selected',
        style: AppTypography.caption.copyWith(color: AppTheme.textMuted),
      ),
    );
  }
}

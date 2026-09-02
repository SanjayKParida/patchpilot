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
    return Container(
      color: AppTheme.surfaceAlt,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _InspectorHeader(title: title, onClose: onClose),
          Divider(height: 1, thickness: 1, color: AppTheme.border),
          Expanded(
            child: child == null
                ? const _InspectorEmptyState()
                : SingleChildScrollView(
                    padding: EdgeInsets.all(AppSpacing.md),
                    child: child,
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
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.sm,
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(
              title,
              style: TextStyle(
                color: AppTheme.text,
                fontWeight: FontWeight.w600,
                fontSize: 13,
                letterSpacing: 0.2,
              ),
            ),
          ),
          if (onClose != null)
            InkWell(
              onTap: onClose,
              borderRadius: BorderRadius.circular(AppRadii.sm),
              child: Padding(
                padding: const EdgeInsets.all(2),
                child: Icon(
                  Icons.close,
                  size: 16,
                  color: AppTheme.textMuted,
                ),
              ),
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
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.lg),
        child: Text(
          'No inspector content for this stage.',
          textAlign: TextAlign.center,
          style: TextStyle(
            color: AppTheme.textMuted,
            fontSize: 12.5,
          ),
        ),
      ),
    );
  }
}
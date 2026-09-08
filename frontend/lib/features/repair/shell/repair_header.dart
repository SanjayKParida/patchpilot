import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';

class RepairHeader extends StatelessWidget implements PreferredSizeWidget {
  const RepairHeader({
    super.key,
    required this.repositoryFullName,
    required this.branch,
    required this.commitSha,
    required this.statusLabel,
    required this.statusColor,
    this.onToggleInspector,
    this.isInspectorVisible = true,
    this.height = 40,
  });

  final String repositoryFullName;
  final String branch;
  final String commitSha;
  final String statusLabel;
  final Color statusColor;
  final VoidCallback? onToggleInspector;
  final bool isInspectorVisible;
  final double height;

  @override
  Size get preferredSize => Size.fromHeight(height);

  String get _shortSha {
    final value = commitSha.trim();
    if (value.isEmpty) return '';
    return value.length > 7 ? value.substring(0, 7) : value;
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: height,
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.shellPadding,
        ),
        child: Row(
          children: [
            const Icon(Icons.terminal, size: 14, color: AppTheme.textMuted),
            const SizedBox(width: 8),
            Expanded(
              child: _RepositoryMetadata(
                repositoryFullName: repositoryFullName,
                branch: branch,
                shortSha: _shortSha,
              ),
            ),
            if (statusLabel.trim().isNotEmpty) ...[
              const SizedBox(width: 12),
              _StatusIndicator(label: statusLabel, color: statusColor),
            ],
            if (onToggleInspector != null) ...[
              const SizedBox(width: 8),
              _InspectorToggle(
                isVisible: isInspectorVisible,
                onTap: onToggleInspector!,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _RepositoryMetadata extends StatelessWidget {
  const _RepositoryMetadata({
    required this.repositoryFullName,
    required this.branch,
    required this.shortSha,
  });

  final String repositoryFullName;
  final String branch;
  final String shortSha;

  @override
  Widget build(BuildContext context) {
    const primary = TextStyle(
      fontFamily: AppTheme.mono,
      fontSize: 12,
      color: AppTheme.text,
      fontWeight: FontWeight.w500,
    );

    const secondary = TextStyle(
      fontFamily: AppTheme.mono,
      fontSize: 11.5,
      color: AppTheme.textMuted,
    );

    return Row(
      children: [
        Flexible(
          child: Text(
            repositoryFullName,
            overflow: TextOverflow.ellipsis,
            style: primary,
          ),
        ),
        const _Sep(),
        Flexible(
          child: Text(
            branch,
            overflow: TextOverflow.ellipsis,
            style: secondary,
          ),
        ),
        if (shortSha.isNotEmpty) ...[
          const _Sep(),
          Flexible(
            child: Text(
              shortSha,
              overflow: TextOverflow.ellipsis,
              style: secondary,
            ),
          ),
        ],
      ],
    );
  }
}

class _StatusIndicator extends StatelessWidget {
  const _StatusIndicator({required this.label, required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 6,
          height: 6,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
        ),
        const SizedBox(width: 6),
        Text(
          label,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: AppTypography.caption.copyWith(color: AppTheme.textSecondary),
        ),
      ],
    );
  }
}

class _InspectorToggle extends StatelessWidget {
  const _InspectorToggle({required this.isVisible, required this.onTap});

  final bool isVisible;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return IconButton(
      onPressed: onTap,
      tooltip: isVisible ? 'Hide inspector' : 'Show inspector',
      icon: Icon(
        isVisible ? Icons.view_sidebar : Icons.view_sidebar_outlined,
        size: 16,
        color: isVisible ? AppTheme.accent : AppTheme.textMuted,
      ),
      padding: EdgeInsets.zero,
      constraints: const BoxConstraints(minWidth: 28, minHeight: 28),
    );
  }
}

class _Sep extends StatelessWidget {
  const _Sep();

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.symmetric(horizontal: 8),
      child: Text(
        '·',
        style: TextStyle(color: AppTheme.borderSubtle, fontSize: 11),
      ),
    );
  }
}

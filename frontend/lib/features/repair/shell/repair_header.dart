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
    this.height = 56,
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
    return Container(
      height: height,
      color: AppTheme.surface,
      padding: const EdgeInsets.symmetric(horizontal: 20),
      child: Row(
        children: [
          _Brand(),
          const SizedBox(width: 18),
          const _Divider(),
          const SizedBox(width: 18),

          Expanded(
            child: _RepositoryMetadata(
              repositoryFullName: repositoryFullName,
              branch: branch,
              shortSha: _shortSha,
            ),
          ),

          const SizedBox(width: 20),

          _StatusIndicator(label: statusLabel, color: statusColor),

          if (onToggleInspector != null) ...[
            const SizedBox(width: 16),
            const _Divider(),
            const SizedBox(width: 12),
            _InspectorToggle(
              isVisible: isInspectorVisible,
              onTap: onToggleInspector!,
            ),
          ],
        ],
      ),
    );
  }
}

class _Brand extends StatelessWidget {
  const _Brand();

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 24,
          height: 24,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: AppTheme.accent,
            borderRadius: BorderRadius.circular(7),
          ),
          child: const Text(
            'P',
            style: TextStyle(
              color: Colors.white,
              fontSize: 13,
              fontWeight: FontWeight.w800,
            ),
          ),
        ),
        const SizedBox(width: 9),
        const Text(
          'PatchPilot',
          style: TextStyle(
            color: AppTheme.text,
            fontSize: 15,
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
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
    const style = TextStyle(
      fontFamily: AppTheme.mono,
      fontSize: 12.5,
      color: AppTheme.text,
    );

    const mutedStyle = TextStyle(
      fontFamily: AppTheme.mono,
      fontSize: 12.5,
      color: AppTheme.textMuted,
    );

    return Row(
      children: [
        Flexible(
          child: Text(
            repositoryFullName,
            overflow: TextOverflow.ellipsis,
            maxLines: 1,
            style: style,
          ),
        ),
        const Padding(
          padding: EdgeInsets.symmetric(horizontal: 8),
          child: Text('·', style: mutedStyle),
        ),
        Flexible(
          child: Text(
            branch,
            overflow: TextOverflow.ellipsis,
            maxLines: 1,
            style: style,
          ),
        ),
        if (shortSha.isNotEmpty) ...[
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 8),
            child: Text('·', style: mutedStyle),
          ),
          Flexible(
            child: Text(
              shortSha,
              overflow: TextOverflow.ellipsis,
              maxLines: 1,
              style: style,
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
          width: 7,
          height: 7,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
        ),
        const SizedBox(width: 7),
        Text(
          label,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(
            color: AppTheme.text,
            fontSize: 12.5,
            fontWeight: FontWeight.w500,
          ),
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
    return TextButton(
      onPressed: onTap,
      style: TextButton.styleFrom(
        foregroundColor: AppTheme.accent,
        padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 6),
        minimumSize: Size.zero,
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
      ),
      child: Text(
        isVisible ? 'Hide inspector' : 'Show inspector',
        style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w500),
      ),
    );
  }
}

class _Divider extends StatelessWidget {
  const _Divider();

  @override
  Widget build(BuildContext context) {
    return const SizedBox(
      height: 20,
      child: VerticalDivider(width: 1, thickness: 1, color: AppTheme.border),
    );
  }
}

import 'package:flutter/material.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/models/models.dart';

/// Compact breadcrumb: back affordance + repository identity.
class RepositoryHeader extends StatelessWidget {
  final Repository repository;
  final VoidCallback onBack;

  const RepositoryHeader({
    super.key,
    required this.repository,
    required this.onBack,
  });

  @override
  Widget build(BuildContext context) {
    final description = repository.description;

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(top: 1),
          child: Material(
            color: Colors.transparent,
            shape: const CircleBorder(),
            child: IconButton(
              onPressed: onBack,
              icon: const Icon(Icons.arrow_back, size: 17),
              tooltip: 'Back to repositories',
              color: AppTheme.textMuted,
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(minWidth: 30, minHeight: 30),
            ),
          ),
        ),
        const SizedBox(width: 6),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                repository.fullName,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  fontSize: 15.5,
                  fontFamily: AppTheme.mono,
                  fontWeight: FontWeight.w600,
                ),
              ),
              if (description != null && description.isNotEmpty) ...[
                const SizedBox(height: 2),
                Text(
                  description,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 12,
                    color: AppTheme.textMuted,
                  ),
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }
}

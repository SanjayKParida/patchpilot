import 'package:flutter/material.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/models/models.dart';

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
    return Row(
      children: [
        IconButton(
          onPressed: onBack,
          icon: const Icon(Icons.arrow_back),
          tooltip: 'Back to repositories',
          color: AppTheme.textMuted,
        ),
        const SizedBox(width: 8),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                repository.fullName,
                style: const TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.w700,
                  letterSpacing: -0.3,
                ),
              ),
              if (repository.description != null &&
                  repository.description!.isNotEmpty) ...[
                const SizedBox(height: 4),
                Text(
                  repository.description!,
                  style: const TextStyle(
                    fontSize: 14,
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

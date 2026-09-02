import 'package:flutter/material.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/core/widgets/common.dart';
import 'package:patchpilot_web/models/models.dart';

class IssueRow extends StatelessWidget {
  final Issue issue;
  final bool analyzeEnabled;
  final VoidCallback onAnalyze;

  const IssueRow({
    super.key,
    required this.issue,
    required this.analyzeEnabled,
    required this.onAnalyze,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Panel(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      StatusChip(
                        label: issue.isOpen ? 'Open' : 'Closed',
                        color: issue.isOpen
                            ? AppTheme.success
                            : AppTheme.purple,
                        icon: issue.isOpen
                            ? Icons.error_outline
                            : Icons.check_circle_outline,
                      ),
                      const SizedBox(width: 10),
                      Text(
                        '#${issue.number}',
                        style: const TextStyle(
                          fontSize: 13,
                          fontFamily: AppTheme.mono,
                          color: AppTheme.textMuted,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Text(
                    issue.title,
                    style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w600,
                      height: 1.4,
                    ),
                  ),
                  if (issue.snippet.isNotEmpty) ...[
                    const SizedBox(height: 6),
                    Text(
                      issue.snippet,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 13,
                        color: AppTheme.textMuted,
                        height: 1.5,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(width: 20),
            FilledButton(
              onPressed: analyzeEnabled ? onAnalyze : null,
              style: FilledButton.styleFrom(
                padding: const EdgeInsets.symmetric(
                  horizontal: 18,
                  vertical: 14,
                ),
              ),
              child: const Text('Analyze'),
            ),
          ],
        ),
      ),
    );
  }
}

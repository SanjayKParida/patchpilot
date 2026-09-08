import 'package:flutter/material.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/models/models.dart';

const _hoverOverlay = Color.fromRGBO(255, 255, 255, 0.04);

/// Triage-oriented issue row: title primary, metadata secondary.
class IssueRow extends StatelessWidget {
  final Issue issue;
  final bool analyzeEnabled;
  final bool analyzed;
  final VoidCallback onAnalyze;

  const IssueRow({
    super.key,
    required this.issue,
    required this.analyzeEnabled,
    required this.onAnalyze,
    this.analyzed = false,
  });

  @override
  Widget build(BuildContext context) {
    final closed = !issue.isOpen;
    final statusColor = closed ? AppTheme.purple : AppTheme.success;

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: analyzeEnabled ? onAnalyze : null,
        hoverColor: _hoverOverlay,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Container(
                  width: 8,
                  height: 8,
                  decoration: BoxDecoration(
                    color: statusColor,
                    shape: BoxShape.circle,
                  ),
                ),
              ),
              const SizedBox(width: 12),
              SizedBox(
                width: 52,
                child: Padding(
                  padding: const EdgeInsets.only(top: 2),
                  child: Text(
                    '#${issue.number}',
                    style: const TextStyle(
                      fontSize: 12,
                      fontFamily: AppTheme.mono,
                      fontWeight: FontWeight.w500,
                      color: AppTheme.textMuted,
                    ),
                  ),
                ),
              ),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      issue.title,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                        height: 1.35,
                        color: closed ? AppTheme.textMuted : AppTheme.text,
                      ),
                    ),
                    if (issue.snippet.isNotEmpty) ...[
                      const SizedBox(height: 4),
                      Text(
                        issue.snippet,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 12,
                          color: AppTheme.textMuted,
                          height: 1.4,
                        ),
                      ),
                    ],
                    const SizedBox(height: 4),
                    Text(
                      closed ? 'Closed' : 'Open',
                      style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w500,
                        color: statusColor,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 16),
              Padding(
                padding: const EdgeInsets.only(top: 2),
                child: analyzed
                    ? const Text(
                        'Analyzed',
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          color: AppTheme.success,
                        ),
                      )
                    : Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            'Analyze',
                            style: TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.w600,
                              color: analyzeEnabled
                                  ? AppTheme.accent
                                  : AppTheme.textMuted,
                            ),
                          ),
                          const SizedBox(width: 4),
                          Icon(
                            Icons.arrow_forward,
                            size: 14,
                            color: analyzeEnabled
                                ? AppTheme.accent
                                : AppTheme.textMuted,
                          ),
                        ],
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class IssueRowSkeleton extends StatelessWidget {
  const IssueRowSkeleton({super.key});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 6),
            child: _bar(width: 8, height: 8, radius: 4),
          ),
          const SizedBox(width: 12),
          _bar(width: 40, height: 12),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _bar(width: double.infinity, height: 14),
                const SizedBox(height: 8),
                _bar(width: 220, height: 11),
              ],
            ),
          ),
          const SizedBox(width: 16),
          _bar(width: 54, height: 12),
        ],
      ),
    );
  }

  Widget _bar({
    required double width,
    required double height,
    double radius = 2,
  }) {
    return Container(
      width: width,
      height: height,
      decoration: BoxDecoration(
        color: AppTheme.surfaceAlt,
        borderRadius: BorderRadius.circular(radius),
      ),
    );
  }
}

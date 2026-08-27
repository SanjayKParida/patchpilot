import 'package:flutter/material.dart';

import '../models/models.dart';
import '../theme.dart';
import '../widgets/common.dart';

/// One ranked file, and — on demand — the reason it is ranked there.
///
/// A ranked list without its reasons is only an assertion. The reasons
/// are behind a disclosure rather than always-on, because the ranking
/// is the primary information and the justification is what you reach
/// for when you doubt it.
class RelevantFileCard extends StatefulWidget {
  final RelevantFile file;
  final int totalSignals;
  final bool cited;
  final void Function({int? line, String? reason}) onOpen;

  const RelevantFileCard({
    super.key,
    required this.file,
    required this.totalSignals,
    required this.cited,
    required this.onOpen,
  });

  @override
  State<RelevantFileCard> createState() => _RelevantFileCardState();
}

class _RelevantFileCardState extends State<RelevantFileCard> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final file = widget.file;

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Panel(
        padding: EdgeInsets.zero,
        borderColor: widget.cited
            ? AppTheme.accent.withValues(alpha: 0.45)
            : AppTheme.border,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _buildRow(file),
            if (_expanded) _buildWhy(file),
          ],
        ),
      ),
    );
  }

  Widget _buildRow(RelevantFile file) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () => widget.onOpen(),
        borderRadius: BorderRadius.circular(10),
        child: Padding(
          padding: const EdgeInsets.symmetric(
            horizontal: 16,
            vertical: 14,
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _rankBadge(file.rank),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Wrap(
                      crossAxisAlignment: WrapCrossAlignment.center,
                      spacing: 8,
                      runSpacing: 4,
                      children: [
                        Text(
                          file.fileName,
                          style: const TextStyle(
                            fontSize: 14,
                            fontWeight: FontWeight.w600,
                            fontFamily: AppTheme.mono,
                          ),
                        ),
                        if (widget.cited)
                          const StatusChip(
                            label: 'cited',
                            color: AppTheme.accent,
                          ),
                      ],
                    ),
                    if (file.directory.isNotEmpty) ...[
                      const SizedBox(height: 3),
                      Text(
                        file.directory,
                        style: const TextStyle(
                          fontSize: 12,
                          fontFamily: AppTheme.mono,
                          color: AppTheme.textMuted,
                        ),
                      ),
                    ],
                    const SizedBox(height: 10),
                    Row(
                      children: [
                        _whyToggle(file),
                        const SizedBox(width: 14),
                        Text(
                          '${file.signalsMatched}/${widget.totalSignals} signals',
                          style: const TextStyle(
                            fontSize: 12,
                            color: AppTheme.textMuted,
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    file.totalScore.toStringAsFixed(2),
                    style: const TextStyle(
                      fontSize: 13,
                      fontFamily: AppTheme.mono,
                      color: AppTheme.textMuted,
                    ),
                  ),
                  const SizedBox(height: 6),
                  const Icon(
                    Icons.code,
                    size: 16,
                    color: AppTheme.textMuted,
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _whyToggle(RelevantFile file) {
    final count = file.evidence.length + file.structural.length;

    return InkWell(
      onTap: count == 0
          ? null
          : () => setState(() => _expanded = !_expanded),
      borderRadius: BorderRadius.circular(4),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 2, horizontal: 2),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              _expanded ? Icons.expand_less : Icons.expand_more,
              size: 16,
              color: count == 0 ? AppTheme.textMuted : AppTheme.accent,
            ),
            const SizedBox(width: 4),
            Text(
              count == 0 ? 'No evidence recorded' : 'Why this file?',
              style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w600,
                color: count == 0 ? AppTheme.textMuted : AppTheme.accent,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _rankBadge(int rank) {
    return Container(
      width: 26,
      height: 26,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: AppTheme.background,
        border: Border.all(color: AppTheme.border),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(
        '$rank',
        style: const TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w700,
          color: AppTheme.textMuted,
        ),
      ),
    );
  }

  Widget _buildWhy(RelevantFile file) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
      decoration: const BoxDecoration(
        color: AppTheme.surfaceAlt,
        borderRadius: BorderRadius.vertical(
          bottom: Radius.circular(9),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (file.evidence.isNotEmpty) ...[
            const SizedBox(height: 12),
            const _WhyHeading('Direct evidence in this file'),
            const SizedBox(height: 8),
            ...file.evidence.map(
              (item) => _EvidenceRow(
                item: item,
                onTap: () => widget.onOpen(
                  line: item.line,
                  reason: '${item.kind} ${item.identifier}',
                ),
              ),
            ),
          ],
          if (file.structural.isNotEmpty) ...[
            const SizedBox(height: 16),
            const _WhyHeading('Structural relationships'),
            const SizedBox(height: 8),
            ...file.structural.map(
              (edge) => Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Row(
                  children: [
                    const Icon(
                      Icons.account_tree_outlined,
                      size: 13,
                      color: AppTheme.purple,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: RichText(
                        text: TextSpan(
                          style: const TextStyle(
                            fontSize: 12.5,
                            color: AppTheme.textMuted,
                            height: 1.5,
                          ),
                          children: [
                            TextSpan(
                              text: edge.relationship,
                              style: const TextStyle(
                                color: AppTheme.purple,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            const TextSpan(text: '  from  '),
                            TextSpan(
                              text: edge.sourceName,
                              style: const TextStyle(
                                fontFamily: AppTheme.mono,
                                color: AppTheme.text,
                              ),
                            ),
                            TextSpan(
                              text: '   distance ${edge.distance}',
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
          const SizedBox(height: 14),
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              onPressed: () => widget.onOpen(),
              icon: const Icon(Icons.code, size: 16),
              label: const Text('Open file'),
              style: TextButton.styleFrom(
                foregroundColor: AppTheme.accent,
                padding: EdgeInsets.zero,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _WhyHeading extends StatelessWidget {
  final String text;

  const _WhyHeading(this.text);

  @override
  Widget build(BuildContext context) {
    return Text(
      text.toUpperCase(),
      style: const TextStyle(
        fontSize: 10,
        fontWeight: FontWeight.w700,
        letterSpacing: 1,
        color: AppTheme.textMuted,
      ),
    );
  }
}

class _EvidenceRow extends StatelessWidget {
  final EvidenceItem item;
  final VoidCallback onTap;

  const _EvidenceRow({required this.item, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(4),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 3),
          child: Row(
            children: [
              SizedBox(
                width: 108,
                child: Text(
                  item.kind,
                  style: const TextStyle(
                    fontSize: 11.5,
                    fontFamily: AppTheme.mono,
                    color: AppTheme.textMuted,
                  ),
                ),
              ),
              Expanded(
                child: Text(
                  item.identifier,
                  style: const TextStyle(
                    fontSize: 12.5,
                    fontFamily: AppTheme.mono,
                    color: AppTheme.text,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Text(
                item.concept,
                style: TextStyle(
                  fontSize: 11.5,
                  color: AppTheme.signalColor('domain'),
                ),
              ),
              const SizedBox(width: 12),
              Text(
                'L${item.line}',
                style: const TextStyle(
                  fontSize: 11.5,
                  fontFamily: AppTheme.mono,
                  color: AppTheme.accent,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

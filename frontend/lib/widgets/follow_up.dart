import 'package:flutter/material.dart';

import '../models/models.dart';
import '../services/api_client.dart';
import '../theme.dart';
import '../widgets/common.dart';

/// Ask one question about the analysis.
///
/// Not a chat. Each question is answered against the analysis's own
/// evidence with no memory of previous questions, which is what keeps
/// every answer grounded in code the pipeline actually looked at.
class FollowUpPanel extends StatefulWidget {
  final ApiClient api;
  final String analysisId;

  const FollowUpPanel({
    super.key,
    required this.api,
    required this.analysisId,
  });

  @override
  State<FollowUpPanel> createState() => _FollowUpPanelState();
}

class _FollowUpPanelState extends State<FollowUpPanel> {
  final _controller = TextEditingController();

  Answer? _answer;
  String? _error;
  bool _loading = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _ask() async {
    final question = _controller.text.trim();
    if (question.isEmpty || _loading) return;

    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final answer = await widget.api.askQuestion(
        widget.analysisId,
        question,
      );

      if (!mounted) return;
      setState(() => _answer = answer);
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const SectionTitle(
          'Ask a follow-up',
          trailing: 'answered from this analysis only',
        ),
        Panel(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _controller,
                      enabled: !_loading,
                      onSubmitted: (_) => _ask(),
                      decoration: const InputDecoration(
                        hintText:
                            'Why is this file ranked first? What would break '
                            'if I change it?',
                        prefixIcon: Icon(
                          Icons.help_outline,
                          color: AppTheme.textMuted,
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  FilledButton(
                    onPressed: _loading ? null : _ask,
                    style: FilledButton.styleFrom(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 20,
                        vertical: 18,
                      ),
                    ),
                    child: _loading
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Colors.white,
                            ),
                          )
                        : const Text('Ask'),
                  ),
                ],
              ),
              if (_error != null) ...[
                const SizedBox(height: 16),
                ErrorNotice(message: _error!),
              ],
              if (_answer != null) ...[
                const SizedBox(height: 20),
                const Divider(height: 1, color: AppTheme.border),
                const SizedBox(height: 20),
                Text(
                  _answer!.question,
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: AppTheme.textMuted,
                  ),
                ),
                const SizedBox(height: 10),
                Text(
                  _answer!.answer,
                  style: const TextStyle(fontSize: 15, height: 1.7),
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }
}

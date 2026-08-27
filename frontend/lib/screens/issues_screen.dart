import 'dart:async';

import 'package:flutter/material.dart';

import '../models/models.dart';
import '../services/api_client.dart';
import '../theme.dart';
import '../widgets/common.dart';

/// Issue list for a repository: the user chooses what to investigate.
class IssuesScreen extends StatefulWidget {
  final ApiClient api;
  final Repository repository;
  final void Function(Issue) onIssueSelected;
  final VoidCallback onBack;

  const IssuesScreen({
    super.key,
    required this.api,
    required this.repository,
    required this.onIssueSelected,
    required this.onBack,
  });

  @override
  State<IssuesScreen> createState() => _IssuesScreenState();
}

class _IssuesScreenState extends State<IssuesScreen> {
  final _searchController = TextEditingController();

  List<Issue> _issues = const [];
  bool _loading = true;
  String? _error;
  String _query = '';

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final issues = await widget.api.listIssues(
        widget.repository.owner,
        widget.repository.repo,
      );

      if (!mounted) return;
      setState(() => _issues = issues);
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  /// Filtering is local: the list is small and the user gets instant
  /// feedback without a request per keystroke.
  List<Issue> get _visible {
    final term = _query.trim().toLowerCase();
    if (term.isEmpty) return _issues;

    return _issues.where((issue) {
      return issue.title.toLowerCase().contains(term) ||
          issue.body.toLowerCase().contains(term) ||
          '#${issue.number}'.contains(term);
    }).toList();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: PageBody(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _buildHeader(),
            const SizedBox(height: 24),
            TextField(
              controller: _searchController,
              onChanged: (value) => setState(() => _query = value),
              decoration: const InputDecoration(
                hintText: 'Filter by number, title or description',
                prefixIcon: Icon(Icons.search, color: AppTheme.textMuted),
              ),
            ),
            const SizedBox(height: 24),
            if (_loading)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 64),
                child: Center(child: CircularProgressIndicator()),
              )
            else if (_error != null)
              ErrorNotice(message: _error!, onRetry: _load)
            else if (_visible.isEmpty)
              EmptyNotice(
                icon: _issues.isEmpty
                    ? Icons.inbox_outlined
                    : Icons.search_off,
                message: _issues.isEmpty
                    ? 'This repository has no open issues.'
                    : 'No issues match "$_query".',
              )
            else ...[
              SectionTitle(
                'Issues',
                trailing: '${_visible.length} of ${_issues.length}',
              ),
              ..._visible.map(_buildIssueRow),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildHeader() {
    return Row(
      children: [
        IconButton(
          onPressed: widget.onBack,
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
                widget.repository.fullName,
                style: const TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.w700,
                  letterSpacing: -0.3,
                ),
              ),
              if (widget.repository.description != null &&
                  widget.repository.description!.isNotEmpty) ...[
                const SizedBox(height: 4),
                Text(
                  widget.repository.description!,
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

  Widget _buildIssueRow(Issue issue) {
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
              onPressed: () => widget.onIssueSelected(issue),
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

import 'package:flutter/material.dart';

import 'models/models.dart';
import 'screens/dashboard_screen.dart';
import 'screens/diagnosis_screen.dart';
import 'screens/issues_screen.dart';
import 'services/analysis_cache.dart';
import 'services/api_client.dart';
import 'theme.dart';

void main() {
  runApp(const PatchPilotApp());
}

class PatchPilotApp extends StatelessWidget {
  const PatchPilotApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'PatchPilot',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.build(),
      home: const AppShell(),
    );
  }
}

/// Navigation for the whole product.
///
/// Dashboard -> Issues -> Diagnosis, with back at every step. A
/// Navigator stack is all this needs; there are three screens and the
/// only shared state is the current repository and issue.
class AppShell extends StatefulWidget {
  const AppShell({super.key});

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  final _api = ApiClient();

  // Session-scoped, so returning to an issue shows the analysis
  // already produced instead of paying for it again.
  final _cache = AnalysisCache();

  final _navigatorKey = GlobalKey<NavigatorState>();

  Repository? _repository;

  void _openIssues(Repository repository) {
    setState(() => _repository = repository);

    _navigatorKey.currentState?.push(
      MaterialPageRoute<void>(
        builder: (_) => IssuesScreen(
          api: _api,
          repository: repository,
          onIssueSelected: _openDiagnosis,
          onBack: () => _navigatorKey.currentState?.pop(),
        ),
      ),
    );
  }

  void _openDiagnosis(Issue issue) {
    final repository = _repository;
    if (repository == null) return;

    _navigatorKey.currentState?.push(
      MaterialPageRoute<void>(
        builder: (_) => DiagnosisScreen(
          api: _api,
          cache: _cache,
          repository: repository,
          issue: issue,
          onBack: () => _navigatorKey.currentState?.pop(),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Navigator(
      key: _navigatorKey,
      onGenerateRoute: (_) => MaterialPageRoute<void>(
        builder: (_) => DashboardScreen(
          api: _api,
          onRepositorySelected: _openIssues,
        ),
      ),
    );
  }
}

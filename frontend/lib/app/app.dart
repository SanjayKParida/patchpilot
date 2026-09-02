import 'package:flutter/material.dart';

import 'package:patchpilot_web/core/theme/app_theme.dart';
import 'package:patchpilot_web/services/api_client.dart';
import 'package:patchpilot_web/services/github_redirect.dart';

import 'shell.dart';

class PatchPilotApp extends StatelessWidget {
  final ApiClient? api;
  final GithubRedirect? redirect;
  final bool? refreshGrantsOnStart;
  final String? initialAuthError;

  const PatchPilotApp({
    super.key,
    this.api,
    this.redirect,
    this.refreshGrantsOnStart,
    this.initialAuthError,
  });

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'PatchPilot',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.build(),
      home: AppShell(
        api: api,
        redirect: redirect,
        refreshGrantsOnStart: refreshGrantsOnStart,
        initialAuthError: initialAuthError,
      ),
    );
  }
}

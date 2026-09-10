/// Builds the URL GitHub should send the browser back to after OAuth.
String? oauthReturnTo({
  required Uri page,
  Uri? route,
  String? analysisId,
}) {
  if (page.scheme != 'http' && page.scheme != 'https') {
    return null;
  }

  final path = (route != null && route.path.isNotEmpty) ? route.path : page.path;
  final normalized = path.isEmpty ? '/' : path;
  final params = Map<String, String>.from(
    (route != null && route.queryParameters.isNotEmpty)
        ? route.queryParameters
        : page.queryParameters,
  );
  params.remove('connected');
  params.remove('auth_error');
  params.remove('analysis_id');
  final resumed = analysisId?.trim();
  if (resumed != null && resumed.isNotEmpty) {
    params['analysis_id'] = resumed;
  }

  return Uri(
    scheme: page.scheme,
    host: page.host,
    port: page.hasPort ? page.port : null,
    path: normalized,
    queryParameters: params.isEmpty ? null : params,
  ).toString();
}

/// Path + query for the OAuth resume record. Null on the dashboard.
String? oauthRepairPath(Uri? route) {
  if (route == null) return null;
  final path = route.path;
  if (path.isEmpty || path == '/') return null;
  if (route.query.isEmpty) return path;
  return '$path?${route.query}';
}

/// Prefer an explicit RepairSession path over the current router URI.
String? oauthResolvedRepairPath(String? repairPath, Uri? route) {
  if (repairPath != null && repairPath.isNotEmpty) return repairPath;
  return oauthRepairPath(route);
}

/// Query values [AppShell] sends to `startGithubLogin`.
class OauthGithubLogin {
  final String? returnTo;
  final String? analysisId;
  final String? stage;
  final String? repairPath;

  const OauthGithubLogin({
    this.returnTo,
    this.analysisId,
    this.stage,
    this.repairPath,
  });
}

/// Resolves OAuth login args, preferring an explicit repair path over `/`.
OauthGithubLogin oauthGithubLogin({
  required Uri page,
  Uri? route,
  String? analysisId,
  String? stage,
  String? repairPath,
}) {
  final resolvedId = analysisId ?? oauthAnalysisId(route);
  final resolvedPath = oauthResolvedRepairPath(repairPath, route);
  final resolvedRoute = (resolvedPath != null && resolvedPath.isNotEmpty)
      ? Uri.parse(resolvedPath)
      : route;
  return OauthGithubLogin(
    returnTo: oauthReturnTo(
      page: page,
      route: resolvedRoute,
      analysisId: resolvedId,
    ),
    analysisId: resolvedId,
    stage: stage ?? oauthStage(resolvedRoute ?? route),
    repairPath: resolvedPath,
  );
}

String? oauthAnalysisId(Uri? route) {
  final id = route?.queryParameters['analysis_id']?.trim();
  if (id == null || id.isEmpty) return null;
  return id;
}

String? oauthStage(Uri? route) {
  if (route == null) return null;
  final parts = route.path.split('/').where((part) => part.isNotEmpty).toList();
  if (parts.length < 6) return null;
  if (parts[0] != 'r' || parts[3] != 'issues') return null;
  final stage = parts[5];
  return stage.isEmpty ? null : stage;
}

/// Session token carried across Flutter web hot restarts.

const sessionStorageKey = 'patchpilot.session';

final _sessionId = RegExp(r'^[a-fA-F0-9]{32}$');

/// Read a PatchPilot session id from a URL fragment (`#session=…`).
///
/// The OAuth callback cannot set a first-party cookie on the Flutter
/// origin (API is another port). The fragment is not sent to the
/// web-server; the app copies it into localStorage and strips it.
String? sessionIdFromFragment(String fragment) {
  var raw = fragment.trim();
  if (raw.startsWith('#')) {
    raw = raw.substring(1);
  }
  if (raw.isEmpty) return null;

  final value = Uri.splitQueryString(raw)['session'] ?? '';
  if (!_sessionId.hasMatch(value)) return null;
  return value.toLowerCase();
}

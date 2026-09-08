import 'github_redirect_stub.dart'
    if (dart.library.js_interop) 'github_redirect_web.dart';

/// Opens GitHub's authorization URL, and other GitHub pages in the
/// browser. Injected in tests.
abstract class GithubRedirect {
  /// Navigate this tab (OAuth / install).
  void go(String url);

  /// Open [url] without leaving the current PatchPilot session.
  void open(String url);

  factory GithubRedirect() = GithubRedirectImpl;
}

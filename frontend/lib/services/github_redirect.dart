import 'github_redirect_stub.dart'
    if (dart.library.js_interop) 'github_redirect_web.dart';

/// Opens GitHub's authorization URL. Injected in tests.
abstract class GithubRedirect {
  void go(String url);

  factory GithubRedirect() = GithubRedirectImpl;
}

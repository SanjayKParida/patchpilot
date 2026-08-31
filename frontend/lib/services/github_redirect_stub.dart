import 'github_redirect.dart';

class GithubRedirectImpl implements GithubRedirect {
  @override
  void go(String url) {
    throw UnsupportedError('GitHub redirect is only available on web');
  }
}

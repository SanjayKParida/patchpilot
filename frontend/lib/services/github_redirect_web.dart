import 'package:web/web.dart' as web;

import 'github_redirect.dart';

class GithubRedirectImpl implements GithubRedirect {
  @override
  void go(String url) {
    web.window.location.href = url;
  }
}

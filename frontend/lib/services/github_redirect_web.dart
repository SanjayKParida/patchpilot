import 'package:web/web.dart' as web;

import 'github_redirect.dart';

class GithubRedirectImpl implements GithubRedirect {
  @override
  void go(String url) {
    web.window.location.href = url;
  }

  @override
  void open(String url) {
    web.window.open(url, '_blank');
  }
}

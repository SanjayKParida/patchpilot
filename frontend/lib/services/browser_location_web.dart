import 'package:web/web.dart' as web;

import 'browser_location.dart';

class BrowserLocationImpl implements BrowserLocation {
  @override
  String get fragment => web.window.location.hash;

  @override
  void replaceWithoutFragment() {
    try {
      final loc = web.window.location;
      final url = '${loc.pathname}${loc.search}';
      web.window.history.replaceState(null, '', url);
    } catch (_) {}
  }
}

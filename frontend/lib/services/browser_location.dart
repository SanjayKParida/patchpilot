import 'browser_location_stub.dart'
    if (dart.library.js_interop) 'browser_location_web.dart';

/// Current page URL helpers that exist only in a browser.
abstract class BrowserLocation {
  String get fragment;

  void replaceWithoutFragment();

  factory BrowserLocation() = BrowserLocationImpl;
}

import 'package:web/web.dart' as web;

import 'key_value_store.dart';

/// Browser implementation.
///
/// Every access is guarded: private windows and blocked site data make
/// localStorage throw, and a convenience feature must never break the
/// page it sits on.
class KeyValueStoreImpl implements KeyValueStore {
  @override
  String? read(String key) {
    try {
      return web.window.localStorage.getItem(key);
    } catch (_) {
      return null;
    }
  }

  @override
  void write(String key, String value) {
    try {
      web.window.localStorage.setItem(key, value);
    } catch (_) {
      // A failed write costs the user nothing important.
    }
  }
}

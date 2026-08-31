import 'key_value_store.dart';

/// Non-web implementation: remembers nothing.
///
/// Used by the Dart VM (tests). Losing a convenience list off the web
/// is the correct trade for keeping the suite runnable.
class KeyValueStoreImpl implements KeyValueStore {
  @override
  String? read(String key) => null;

  @override
  void write(String key, String value) {}

  @override
  void remove(String key) {}
}

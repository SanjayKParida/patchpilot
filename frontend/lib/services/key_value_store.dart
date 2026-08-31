import 'key_value_store_stub.dart'
    if (dart.library.js_interop) 'key_value_store_web.dart';

/// Tiny key/value store, backed by browser localStorage on the web.
///
/// Behind a conditional import because `package:web` needs
/// `dart:js_interop`, which does not exist on the Dart VM. Without
/// this, importing anything that touches storage makes `flutter test`
/// fail to compile — the app must stay testable on the default
/// platform, not only in a browser.
abstract class KeyValueStore {
  String? read(String key);
  void write(String key, String value);
  void remove(String key);

  factory KeyValueStore() = KeyValueStoreImpl;
}


class MemoryKeyValueStore implements KeyValueStore {
  final Map<String, String> _data = {};

  @override
  String? read(String key) => _data[key];

  @override
  void write(String key, String value) => _data[key] = value;

  @override
  void remove(String key) => _data.remove(key);
}

import 'dart:convert';

import '../models/models.dart';
import 'key_value_store.dart';

/// Remembers the last few repositories analysed, on this device only.
///
/// A convenience, not state the product depends on: anything unreadable
/// is treated as "no history" rather than surfaced as an error.
class RecentRepositories {
  static const String _key = 'patchpilot.recent_repositories';
  static const int _limit = 5;

  final KeyValueStore _store;

  RecentRepositories({KeyValueStore? store})
      : _store = store ?? KeyValueStore();

  List<Repository> load() {
    final raw = _store.read(_key);
    if (raw == null || raw.isEmpty) return const [];

    try {
      final decoded = jsonDecode(raw);
      if (decoded is! List) return const [];

      return decoded
          .whereType<Map<String, dynamic>>()
          .map(Repository.fromJson)
          .toList();
    } catch (_) {
      return const [];
    }
  }

  List<Repository> add(Repository repository) {
    final existing =
        load().where((r) => r.fullName != repository.fullName).toList();

    final updated = [repository, ...existing].take(_limit).toList();

    _store.write(
      _key,
      jsonEncode(updated.map((r) => r.toJson()).toList()),
    );

    return updated;
  }
}

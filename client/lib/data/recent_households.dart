/// Recently viewed households (wireframe 4.12a).
///
/// IR-07: this is the only thing the client stores, and it is not personal
/// data — a household id is an opaque sandbox code such as "h015". No name,
/// amount or forecast is ever written to the device.
library;

import 'package:shared_preferences/shared_preferences.dart';

abstract interface class RecentHouseholds {
  Future<List<String>> load();

  /// Moves [userId] to the front and returns the updated list.
  Future<List<String>> add(String userId);
}

const _maxRecent = 5;

List<String> _pushFront(List<String> current, String userId) =>
    [userId, ...current.where((id) => id != userId)].take(_maxRecent).toList();

class PreferencesRecentHouseholds implements RecentHouseholds {
  static const _key = 'recent_households';

  @override
  Future<List<String>> load() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getStringList(_key) ?? const [];
  }

  @override
  Future<List<String>> add(String userId) async {
    final prefs = await SharedPreferences.getInstance();
    final updated = _pushFront(prefs.getStringList(_key) ?? const [], userId);
    await prefs.setStringList(_key, updated);
    return updated;
  }
}

/// Keeps nothing beyond the running app. Used by tests.
class InMemoryRecentHouseholds implements RecentHouseholds {
  InMemoryRecentHouseholds([List<String> initial = const []])
    : _ids = List.of(initial);

  List<String> _ids;

  @override
  Future<List<String>> load() async => List.unmodifiable(_ids);

  @override
  Future<List<String>> add(String userId) async =>
      List.unmodifiable(_ids = _pushFront(_ids, userId));
}

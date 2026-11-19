/// The signed-in demo household, and the actions that build its history.
///
/// Every action that changes the household's data hands the new month in
/// progress to the [ForecastController], which drops what it had loaded and
/// fetches the forecast again, so the screens always show the household as
/// it now is.
library;

import 'package:decimal/decimal.dart';
import 'package:flutter/foundation.dart';

import '../data/api_exception.dart';
import '../data/demo.dart';
import 'forecast_controller.dart';

class DemoController extends ChangeNotifier {
  DemoController({required DemoApi api, required ForecastController forecast})
    : _client = api,
      _screens = forecast;

  final DemoApi _client;
  final ForecastController _screens;

  DemoHousehold? _household;
  DemoCategories? _categories;
  bool _busy = false;
  ApiException? _error;
  bool _disposed = false;

  DemoHousehold? get household => _household;
  DemoCategories? get categories => _categories;
  bool get busy => _busy;

  /// The last action's failure, until the next action starts.
  ApiException? get error => _error;

  /// Whether the household on screen is this demo household.
  bool isShowing(String? householdId) =>
      householdId != null && _household?.userId == householdId;

  Future<bool> signup(String name, String pin) =>
      _act(() => _client.signup(name.trim(), pin));

  Future<bool> login(String name, String pin) =>
      _act(() => _client.login(name.trim(), pin));

  Future<void> loadCategories() async {
    if (_categories != null) return;
    try {
      _categories = await _client.getDemoCategories();
    } on ApiException catch (error) {
      _error = error;
    }
    _notify();
  }

  Future<bool> saveBudget(Map<String, Decimal> allocated) =>
      _act(() => _client.saveBudget(_household!.userId, allocated), refresh: true);

  Future<bool> addSpend(String category, Decimal amount) => _act(
    () => _client.addSpend(_household!.userId, category, amount),
    refresh: true,
  );

  Future<bool> simulate(int months) =>
      _act(() => _client.simulate(_household!.userId, months), refresh: true);

  /// Opens the forecast screens on the household's month in progress.
  Future<void> enter() {
    final h = _household!;
    return _screens.selectHousehold(
      h.userId,
      h.month,
      lastMonth: h.lastCompleteMonth,
    );
  }

  void signOut() {
    _household = null;
    _error = null;
    _notify();
    _screens.changeHousehold();
  }

  /// Runs one request. [refresh] reloads the forecast screens when they are
  /// showing this household.
  Future<bool> _act(
    Future<DemoHousehold> Function() request, {
    bool refresh = false,
  }) async {
    _busy = true;
    _error = null;
    _notify();
    try {
      final household = await request();
      _household = household;
      if (refresh && isShowing(_screens.householdId)) {
        // Not awaited: the forecast has its own loading state on screen.
        _screens.reload(
          household.month,
          lastMonth: household.lastCompleteMonth,
        );
      }
      return true;
    } on ApiException catch (error) {
      _error = error;
      return false;
    } catch (error) {
      _error = ApiException.invalidResponse('$error');
      return false;
    } finally {
      _busy = false;
      _notify();
    }
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}

/// The single source of state for every screen (§4.4.3), and the state
/// machine of Figure 4.8:
///
///   Idle --select household--> Loading --200, riskFlag null--> Loaded
///                                      --200, riskFlag set---> Loaded, flagged
///                                      --422/timeout/network/5xx--> Error
///   Loaded, flagged --change month--> Loading
///   Loaded --change month / open comparison--> Loading
///   Error --retry--> Loading
///   Loaded --change household--> Idle
///
/// "Loaded, flagged" is [LoadState.loaded] with a non-null riskFlag, read from
/// the result rather than duplicated as a state. "Waking up" is not a state
/// either: it is [Loadable.waking], raised while still loading once
/// [wakingAfter] has passed (IR-04), because the request in flight is the
/// same one and nothing about it has changed except how long it has taken.
library;

import 'dart:async';

import 'package:decimal/decimal.dart';
import 'package:flutter/foundation.dart';

import '../data/api_exception.dart';
import '../data/forecast_api.dart';
import '../data/models.dart';
import '../data/recent_households.dart';

enum LoadState { idle, loading, loaded, error }

/// One request's lifecycle: its state, its result or error, and whether it
/// has been slow enough to say the service is waking up.
class Loadable<T> {
  LoadState _state = LoadState.idle;
  T? _value;
  ApiException? _error;
  bool _waking = false;
  Timer? _timer;

  /// Incremented per request, so a slow earlier answer cannot overwrite a
  /// later one when the user steps months faster than the service replies.
  int _ticket = 0;

  LoadState get state => _state;
  T? get value => _value;
  ApiException? get error => _error;
  bool get waking => _waking;
  bool get isLoading => _state == LoadState.loading;

  void _reset() {
    _timer?.cancel();
    _ticket++;
    _state = LoadState.idle;
    _value = null;
    _error = null;
    _waking = false;
  }
}

class ForecastController extends ChangeNotifier {
  ForecastController({
    required ForecastApi api,
    required RecentHouseholds recent,
    this.dataLastMonth,
    this.wakingAfter = const Duration(seconds: 5),
  }) : _client = api,
       _recentStore = recent;

  final ForecastApi _client;
  final RecentHouseholds _recentStore;

  /// From --dart-define=DATA_LAST_MONTH; see AppConfig for the limitation.
  final YearMonth? dataLastMonth;

  /// IR-04: when to tell the user the service is waking up.
  final Duration wakingAfter;

  /// How many months the comparison shows before and after the selected one,
  /// as in wireframe 4.14e (Jul-Nov around October).
  static const comparisonBefore = 3;
  static const comparisonAfter = 1;

  String? _householdId;
  YearMonth? _month;
  List<String> _recent = const [];
  bool _disposed = false;

  final forecast = Loadable<ForecastResult>();
  final budget = Loadable<BudgetResult>();
  final comparison = Loadable<List<MonthForecast>>();

  /// The month the current comparison was loaded around, so it reloads only
  /// when the selected month has actually changed.
  YearMonth? _comparisonCentre;

  String? get householdId => _householdId;
  YearMonth? get month => _month;
  List<String> get recentHouseholds => _recent;

  /// The state of Figure 4.8, which is the state of the forecast request.
  LoadState get state => forecast.state;

  Future<void> loadRecent() async {
    _recent = await _recentStore.load();
    _notify();
  }

  /// Idle -> Loading. Clears everything belonging to the previous household.
  Future<void> selectHousehold(String id, YearMonth month) async {
    final userId = id.trim();
    _householdId = userId;
    _month = month;
    budget._reset();
    comparison._reset();
    _comparisonCentre = null;
    final load = loadForecast();
    _recent = await _recentStore.add(userId);
    _notify();
    await load;
  }

  /// Loaded -> Idle ("change household").
  void changeHousehold() {
    _householdId = null;
    _month = null;
    forecast._reset();
    budget._reset();
    comparison._reset();
    _comparisonCentre = null;
    _notify();
  }

  /// Steps the selected month without returning to the household screen.
  Future<void> changeMonth(int delta) {
    _month = _month!.plus(delta);
    return loadForecast();
  }

  Future<void> loadForecast() => _run(
    forecast,
    () => _client.getForecast(_householdId!, _month!.month, _month!.year),
  );

  /// The budget belongs to the household, not the month: loaded once per
  /// household unless [force]d by a retry.
  Future<void> loadBudget({bool force = false}) async {
    if (!force && budget.state != LoadState.idle) return;
    await _run(budget, () => _client.getBudget(_householdId!));
  }

  /// Point and range for consecutive months around the selected one (FR-14).
  Future<void> loadComparison({bool force = false}) async {
    if (!force &&
        _comparisonCentre == _month &&
        comparison.state != LoadState.idle) {
      return;
    }
    _comparisonCentre = _month;
    final months = [
      for (var i = -comparisonBefore; i <= comparisonAfter; i++)
        _month!.plus(i),
    ];
    final userId = _householdId!;
    await _run(comparison, () async {
      final results = await Future.wait([
        for (final m in months) _client.getForecast(userId, m.month, m.year),
      ]);
      return [
        for (var i = 0; i < months.length; i++)
          MonthForecast(
            month: months[i],
            result: results[i],
            afterDataEnd: isAfterDataEnd(months[i]),
          ),
      ];
    });
  }

  /// Drawn dashed in the month comparison.
  ///
  /// The month straight after the data ends is the genuine forecast — the one
  /// the service exists to make — so it is drawn solid. Every month after
  /// that is forecast from exactly the same history and adds no information
  /// (§4.4.9), so those are dashed. Wireframe 4.14e shows the same: data to
  /// September, October solid, November dashed.
  ///
  /// False for every month when DATA_LAST_MONTH was not supplied.
  bool isAfterDataEnd(YearMonth month) {
    final last = dataLastMonth;
    return last != null && month.isAfter(last.plus(1));
  }

  /// FR-13, computed here because the service does not flag overspending and
  /// is not to be changed to: every category whose forecast exceeds the
  /// declared budget. Categories with no declared budget cannot exceed one.
  List<String> categoriesOverBudget() {
    final result = forecast.value;
    final allocated = budget.value?.allocated;
    if (result == null || allocated == null) return const [];
    return [
      for (final entry in result.breakdownLargestFirst)
        if (allocated[entry.key] case final Decimal limit
            when entry.value > limit)
          entry.key,
    ];
  }

  Future<void> _run<T>(Loadable<T> slot, Future<T> Function() fetch) async {
    slot._timer?.cancel();
    final ticket = ++slot._ticket;
    slot
      .._state = LoadState.loading
      .._error = null
      .._waking = false;
    slot._timer = Timer(wakingAfter, () {
      if (slot._ticket == ticket && slot.isLoading) {
        slot._waking = true;
        _notify();
      }
    });
    _notify();

    try {
      final value = await fetch();
      if (slot._ticket != ticket) return;
      slot
        .._value = value
        .._state = LoadState.loaded;
    } on ApiException catch (error) {
      if (slot._ticket != ticket) return;
      slot
        .._error = error
        .._state = LoadState.error;
    } catch (error) {
      if (slot._ticket != ticket) return;
      slot
        .._error = ApiException.invalidResponse('$error')
        .._state = LoadState.error;
    } finally {
      if (slot._ticket == ticket) {
        slot._timer?.cancel();
        slot._waking = false;
      }
    }
    _notify();
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    for (final slot in [forecast, budget, comparison]) {
      slot._timer?.cancel();
    }
    super.dispose();
  }
}

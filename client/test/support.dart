/// Shared test doubles and fixtures. No test makes a network call: every
/// widget test runs against [FakeForecastApi].
///
/// The fixtures are the service's own responses, captured from the running
/// container (data/public slice): h015 for October 2026 is Figure 4.10.
library;

import 'dart:async';

import 'package:budget_forecast_client/data/api_exception.dart';
import 'package:budget_forecast_client/data/forecast_api.dart';
import 'package:budget_forecast_client/data/models.dart';
import 'package:budget_forecast_client/data/recent_households.dart';
import 'package:budget_forecast_client/presentation/app.dart';
import 'package:budget_forecast_client/state/forecast_controller.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';

const h015October = {
  'estimatedTotal': 66284.77,
  'breakdown': {
    'Airtime and Data': 2612.64,
    'Medical': 1687.58,
    'Rent': 19215.09,
    'Household Help': 4001.29,
    'Savings': 3425.76,
    'Utilities': 4015.24,
    'Groceries': 13627.6,
    'School Fees': 7873.33,
    'Entertainment': 2044.6,
    'Transport': 7722.8,
    'Electronics Upgrade': 58.84,
  },
  'confidence': 0.7825,
  'riskFlag': null,
  'estimatedTotalLow': 55658.27,
  'estimatedTotalHigh': 75070.63,
  'isSynthetic': true,
  'method': 'blend:history0.8_budget0.2',
};

const h015Budget = {
  'userId': 'h015',
  'allocated': {
    'Airtime and Data': 2867.0,
    'Electronics Upgrade': 0.0,
    'Entertainment': 2867.0,
    'Groceries': 12900.0,
    'Household Help': 4300.0,
    'Medical': 3583.0,
    'Rent': 21499.0,
    'Savings': 3583.0,
    'School Fees': 8600.0,
    'Transport': 7166.0,
    'Utilities': 4300.0,
  },
  'isSynthetic': true,
};

/// What the service returns for an unknown household (and for fewer than
/// three months of history).
const insufficient = {
  'estimatedTotal': 0.0,
  'breakdown': <String, double>{},
  'confidence': 0.0,
  'riskFlag': 'insufficient_history',
  'estimatedTotalLow': null,
  'estimatedTotalHigh': null,
  'isSynthetic': true,
  'method': 'blend:history0.8_budget0.2 (no history for user)',
};

const emptyBudget = {
  'userId': 'nobody',
  'allocated': <String, double>{},
  'isSynthetic': true,
};

Map<String, Object?> withFlag(String? flag) => {
  ...h015October,
  'riskFlag': flag,
};

/// A forecast whose total differs by month, so tests can tell months apart.
Map<String, Object?> forMonth(int month) => {
  ...h015October,
  'estimatedTotal': 60000.0 + month * 1000,
  'breakdown': {'Rent': 30000.0, 'Food': 30000.0 + month * 1000},
  'estimatedTotalLow': 50000.0 + month * 1000,
  'estimatedTotalHigh': 70000.0 + month * 1000,
};

const network = ApiException(
  ApiErrorKind.network,
  'Could not reach the service (Connection refused).',
);
const timeout = ApiException(
  ApiErrorKind.timeout,
  'The service did not answer within 60 seconds.',
);
const invalid = ApiException(
  ApiErrorKind.validation,
  '"month" was rejected by the service: Input should be less than or equal to 12.',
  field: 'month',
);
const serverError = ApiException(
  ApiErrorKind.server,
  'The service failed with HTTP 503.',
);

typedef ForecastHandler = FutureOr<Object?> Function(
  String userId,
  int month,
  int year,
);
typedef BudgetHandler = FutureOr<Object?> Function(String userId);

/// Handlers return a JSON map (parsed exactly as the real client parses it),
/// or throw an [ApiException].
class FakeForecastApi implements ForecastApi {
  FakeForecastApi({ForecastHandler? forecast, BudgetHandler? budget})
    : forecast = forecast ?? ((_, _, _) => h015October),
      budget = budget ?? ((_) => h015Budget);

  ForecastHandler forecast;
  BudgetHandler budget;
  final forecastCalls = <String>[];
  final budgetCalls = <String>[];

  @override
  Future<ForecastResult> getForecast(String userId, int month, int year) async {
    forecastCalls.add('$userId $year-$month');
    return ForecastResult.fromJson(await forecast(userId, month, year));
  }

  @override
  Future<BudgetResult> getBudget(String userId) async {
    budgetCalls.add(userId);
    return BudgetResult.fromJson(await budget(userId));
  }
}

const september2026 = YearMonth(2026, 9);
const october2026 = YearMonth(2026, 10);

/// Phone portrait, tall enough that list content is built without scrolling.
const tallPhone = Size(420, 2000);
const desktop = Size(1280, 1400);

Future<ForecastController> pumpApp(
  WidgetTester tester, {
  FakeForecastApi? api,
  Size size = tallPhone,
  YearMonth? dataLastMonth = september2026,
  List<String> recent = const [],
}) async {
  tester.view
    ..devicePixelRatio = 1.0
    ..physicalSize = size;
  addTearDown(tester.view.reset);

  final controller = ForecastController(
    api: api ?? FakeForecastApi(),
    recent: InMemoryRecentHouseholds(recent),
    dataLastMonth: dataLastMonth,
  );
  addTearDown(controller.dispose);
  await controller.loadRecent();
  await tester.pumpWidget(BudgetForecastApp(controller: controller));
  return controller;
}

/// Household selection -> dashboard for [id], via the real form.
Future<void> showForecast(WidgetTester tester, String id) async {
  await tester.enterText(find.byKey(const Key('household-id')), id);
  await tester.tap(find.byKey(const Key('show-forecast')));
  await tester.pumpAndSettle();
}

Finder textContaining(String text) => find.textContaining(text);

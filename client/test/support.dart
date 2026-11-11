/// Shared test doubles and fixtures. No test makes a network call: every
/// widget test runs against [FakeForecastApi].
///
/// The fixtures are the service's own responses, captured from the running
/// container (data/public slice): h015 for October 2026 is Figure 4.10.
library;

import 'dart:async';

import 'package:budget_forecast_client/data/api_exception.dart';
import 'package:budget_forecast_client/data/forecast_api.dart';
import 'package:budget_forecast_client/data/insights.dart';
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

/// GET /insights for h015, October 2026, from the same slice. Its calendar is
/// close to even and it has no discretionary spending, as most households do.
const h015Insights = {
  "userId": "h015",
  "month": 10,
  "year": 2026,
  "historyMonths": 18,
  "usual": {
    "months": ["2026-07", "2026-08", "2026-09"],
    "total": 57159.0,
    "breakdown": {
      "Rent": 15247.0,
      "Groceries": 12971.0,
      "School Fees": 7273.0,
      "Transport": 6908.0,
      "Utilities": 4014.0,
      "Household Help": 3610.0,
      "Savings": 3050.0,
      "Airtime and Data": 2045.0,
      "Entertainment": 2041.0,
    },
  },
  "calendar": {
    "months": [
      "2025-10",
      "2025-11",
      "2025-12",
      "2026-01",
      "2026-02",
      "2026-03",
      "2026-04",
      "2026-05",
      "2026-06",
      "2026-07",
      "2026-08",
      "2026-09",
    ],
    "monthParts": [
      {
        "firstDay": 1,
        "lastDay": 7,
        "share": 0.2424,
        "evenShare": 0.2303,
        "standsOut": false,
        "averageAmount": 15381.42,
      },
      {
        "firstDay": 8,
        "lastDay": 14,
        "share": 0.2829,
        "evenShare": 0.2303,
        "standsOut": false,
        "averageAmount": 17956.5,
      },
      {
        "firstDay": 15,
        "lastDay": 21,
        "share": 0.243,
        "evenShare": 0.2303,
        "standsOut": false,
        "averageAmount": 15418.58,
      },
      {
        "firstDay": 22,
        "lastDay": 31,
        "share": 0.2317,
        "evenShare": 0.309,
        "standsOut": false,
        "averageAmount": 14706.08,
      },
    ],
    "weekdays": [
      {
        "weekday": 1,
        "share": 0.1577,
        "evenShare": 0.1425,
        "standsOut": false,
        "averageAmount": 10009.08,
      },
      {
        "weekday": 2,
        "share": 0.1714,
        "evenShare": 0.1425,
        "standsOut": false,
        "averageAmount": 10875.33,
      },
      {
        "weekday": 3,
        "share": 0.1686,
        "evenShare": 0.1452,
        "standsOut": false,
        "averageAmount": 10697.83,
      },
      {
        "weekday": 4,
        "share": 0.1167,
        "evenShare": 0.1425,
        "standsOut": false,
        "averageAmount": 7407.83,
      },
      {
        "weekday": 5,
        "share": 0.1078,
        "evenShare": 0.1424,
        "standsOut": false,
        "averageAmount": 6838.75,
      },
      {
        "weekday": 6,
        "share": 0.1872,
        "evenShare": 0.1425,
        "standsOut": false,
        "averageAmount": 11880.92,
      },
      {
        "weekday": 7,
        "share": 0.0906,
        "evenShare": 0.1425,
        "standsOut": false,
        "averageAmount": 5752.83,
      },
    ],
  },
  "discretionary": {
    "categories": [
      "Gambling",
      "Crypto Purchase",
      "Cash Advance",
      "Luxury Goods",
    ],
    "months": [
      {
        "month": "2025-10",
        "total": 62619.0,
        "amount": 0.0,
        "share": 0.0,
        "byCategory": {
          "Gambling": 0.0,
          "Crypto Purchase": 0.0,
          "Cash Advance": 0.0,
          "Luxury Goods": 0.0,
        },
      },
      {
        "month": "2025-11",
        "total": 82066.0,
        "amount": 0.0,
        "share": 0.0,
        "byCategory": {
          "Gambling": 0.0,
          "Crypto Purchase": 0.0,
          "Cash Advance": 0.0,
          "Luxury Goods": 0.0,
        },
      },
      {
        "month": "2025-12",
        "total": 63348.0,
        "amount": 0.0,
        "share": 0.0,
        "byCategory": {
          "Gambling": 0.0,
          "Crypto Purchase": 0.0,
          "Cash Advance": 0.0,
          "Luxury Goods": 0.0,
        },
      },
      {
        "month": "2026-01",
        "total": 63693.0,
        "amount": 0.0,
        "share": 0.0,
        "byCategory": {
          "Gambling": 0.0,
          "Crypto Purchase": 0.0,
          "Cash Advance": 0.0,
          "Luxury Goods": 0.0,
        },
      },
      {
        "month": "2026-02",
        "total": 63351.0,
        "amount": 0.0,
        "share": 0.0,
        "byCategory": {
          "Gambling": 0.0,
          "Crypto Purchase": 0.0,
          "Cash Advance": 0.0,
          "Luxury Goods": 0.0,
        },
      },
      {
        "month": "2026-03",
        "total": 60797.0,
        "amount": 0.0,
        "share": 0.0,
        "byCategory": {
          "Gambling": 0.0,
          "Crypto Purchase": 0.0,
          "Cash Advance": 0.0,
          "Luxury Goods": 0.0,
        },
      },
      {
        "month": "2026-04",
        "total": 63080.0,
        "amount": 0.0,
        "share": 0.0,
        "byCategory": {
          "Gambling": 0.0,
          "Crypto Purchase": 0.0,
          "Cash Advance": 0.0,
          "Luxury Goods": 0.0,
        },
      },
      {
        "month": "2026-05",
        "total": 66867.0,
        "amount": 0.0,
        "share": 0.0,
        "byCategory": {
          "Gambling": 0.0,
          "Crypto Purchase": 0.0,
          "Cash Advance": 0.0,
          "Luxury Goods": 0.0,
        },
      },
      {
        "month": "2026-06",
        "total": 59450.0,
        "amount": 0.0,
        "share": 0.0,
        "byCategory": {
          "Gambling": 0.0,
          "Crypto Purchase": 0.0,
          "Cash Advance": 0.0,
          "Luxury Goods": 0.0,
        },
      },
      {
        "month": "2026-07",
        "total": 50999.0,
        "amount": 0.0,
        "share": 0.0,
        "byCategory": {
          "Gambling": 0.0,
          "Crypto Purchase": 0.0,
          "Cash Advance": 0.0,
          "Luxury Goods": 0.0,
        },
      },
      {
        "month": "2026-08",
        "total": 63848.0,
        "amount": 0.0,
        "share": 0.0,
        "byCategory": {
          "Gambling": 0.0,
          "Crypto Purchase": 0.0,
          "Cash Advance": 0.0,
          "Luxury Goods": 0.0,
        },
      },
      {
        "month": "2026-09",
        "total": 61433.0,
        "amount": 0.0,
        "share": 0.0,
        "byCategory": {
          "Gambling": 0.0,
          "Crypto Purchase": 0.0,
          "Cash Advance": 0.0,
          "Luxury Goods": 0.0,
        },
      },
    ],
  },
  "isSynthetic": true,
};

/// h015 with one month of discretionary spending, to exercise that chart.
Map<String, Object?> withDiscretionaryIn(String month, double amount) {
  final trend = h015Insights['discretionary']! as Map<String, Object?>;
  return {
    ...h015Insights,
    'discretionary': {
      ...trend,
      'months': [
        for (final m in trend['months']! as List)
          if ((m as Map)['month'] == month)
            {
              ...m.cast<String, Object?>(),
              'amount': amount,
              'share': amount / (m['total'] as num),
              'byCategory': {
                'Gambling': 0.0,
                'Crypto Purchase': 0.0,
                'Cash Advance': amount,
                'Luxury Goods': 0.0,
              },
            }
          else
            m,
      ],
    },
  };
}

/// GET /insights for an unknown household.
const insufficientInsights = {
  'userId': 'nobody',
  'month': 10,
  'year': 2026,
  'historyMonths': 0,
  'usual': null,
  'calendar': null,
  'discretionary': null,
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
typedef InsightsHandler = FutureOr<Object?> Function(
  String userId,
  int month,
  int year,
);

/// Handlers return a JSON map (parsed exactly as the real client parses it),
/// or throw an [ApiException].
class FakeForecastApi implements ForecastApi {
  FakeForecastApi({
    ForecastHandler? forecast,
    BudgetHandler? budget,
    InsightsHandler? insights,
  }) : forecast = forecast ?? ((_, _, _) => h015October),
       budget = budget ?? ((_) => h015Budget),
       insights = insights ?? ((_, _, _) => h015Insights);

  ForecastHandler forecast;
  BudgetHandler budget;
  InsightsHandler insights;
  final forecastCalls = <String>[];
  final budgetCalls = <String>[];
  final insightsCalls = <String>[];

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

  @override
  Future<InsightsResult> getInsights(String userId, int month, int year) async {
    insightsCalls.add('$userId $year-$month');
    return InsightsResult.fromJson(await insights(userId, month, year));
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

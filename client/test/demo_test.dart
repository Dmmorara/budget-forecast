// Demo households: sign up, declare a budget, build up history, and see the
// forecast screens follow along. Against a fake of the /demo endpoints.

import 'package:budget_forecast_client/data/api_exception.dart';
import 'package:budget_forecast_client/data/demo.dart';
import 'package:budget_forecast_client/data/models.dart';
import 'package:budget_forecast_client/data/recent_households.dart';
import 'package:budget_forecast_client/presentation/app.dart';
import 'package:budget_forecast_client/state/demo_controller.dart';
import 'package:budget_forecast_client/state/forecast_controller.dart';
import 'package:decimal/decimal.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

/// The service's rules in miniature: a household starts in October 2026,
/// and each simulated month moves it on by one.
class FakeDemoApi implements DemoApi {
  final households = <String, Map<String, Object?>>{};
  final pins = <String, String>{};
  final calls = <String>[];

  Map<String, Object?> _fresh(String name) => {
    'userId': 'demo-${households.length + 1}',
    'name': name,
    'month': 10,
    'year': 2026,
    'historyMonths': 0,
    'budget': <String, double>{},
    'spentThisMonth': <String, double>{},
    'isSynthetic': true,
  };

  @override
  Future<DemoCategories> getDemoCategories() async => DemoCategories.fromJson({
    'categories': ['Gambling', 'Groceries', 'Rent'],
    'typical': {'Groceries': 12800.0, 'Rent': 21300.0},
  });

  @override
  Future<DemoHousehold> signup(String name, String pin) async {
    calls.add('signup $name');
    final h = _fresh(name);
    households[h['userId']! as String] = h;
    pins[name] = pin;
    return DemoHousehold.fromJson(h);
  }

  @override
  Future<DemoHousehold> login(String name, String pin) async {
    calls.add('login $name');
    final h = households.values.where((h) => h['name'] == name).firstOrNull;
    if (h == null || pins[name] != pin) {
      throw const ApiException(
        ApiErrorKind.validation,
        'No demo household matches that name and PIN.',
      );
    }
    return DemoHousehold.fromJson(h);
  }

  @override
  Future<DemoHousehold> saveBudget(
    String userId,
    Map<String, Decimal> allocated,
  ) async {
    calls.add('budget $userId');
    final h = households[userId]!;
    h['budget'] = {
      for (final e in allocated.entries) e.key: e.value.toDouble(),
    };
    return DemoHousehold.fromJson(h);
  }

  @override
  Future<DemoHousehold> addSpend(
    String userId,
    String category,
    Decimal amount,
  ) async {
    calls.add('spend $userId $category $amount');
    final h = households[userId]!;
    h['spentThisMonth'] = {
      ...(h['spentThisMonth']! as Map<String, double>),
      category: amount.toDouble(),
    };
    return DemoHousehold.fromJson(h);
  }

  @override
  Future<DemoHousehold> simulate(String userId, int months) async {
    calls.add('simulate $userId $months');
    final h = households[userId]!;
    final next = YearMonth(h['year']! as int, h['month']! as int).plus(months);
    h
      ..['year'] = next.year
      ..['month'] = next.month
      ..['historyMonths'] = (h['historyMonths']! as int) + months
      ..['spentThisMonth'] = <String, double>{};
    return DemoHousehold.fromJson(h);
  }
}

/// A demo household is forecast only once it has three months of history,
/// i.e. from January 2027.
FakeForecastApi demoForecasts() => FakeForecastApi(
  forecast: (userId, month, year) =>
      year * 12 + month < 2027 * 12 + 1 ? insufficient : h015October,
  budget: (userId) => emptyBudget,
  insights: (userId, month, year) => insufficientInsights,
);

Future<(ForecastController, DemoController)> pumpDemoApp(
  WidgetTester tester, {
  required FakeForecastApi api,
  required FakeDemoApi demoApi,
}) async {
  tester.view
    ..devicePixelRatio = 1.0
    ..physicalSize = tallPhone;
  addTearDown(tester.view.reset);

  final controller = ForecastController(
    api: api,
    recent: InMemoryRecentHouseholds(),
    dataLastMonth: september2026,
  );
  final demo = DemoController(api: demoApi, forecast: controller);
  addTearDown(controller.dispose);
  addTearDown(demo.dispose);
  await tester.pumpWidget(
    BudgetForecastApp(controller: controller, demo: demo),
  );
  return (controller, demo);
}

Future<void> signUp(WidgetTester tester, {String pin = '1234'}) async {
  await tester.tap(find.byKey(const Key('open-demo')));
  await tester.pumpAndSettle();
  await tester.enterText(find.byKey(const Key('demo-name')), 'The Otienos');
  await tester.enterText(find.byKey(const Key('demo-pin')), pin);
  await tester.tap(find.byKey(const Key('demo-submit')));
  await tester.pumpAndSettle();
}

Future<void> signUpWithTypicalBudget(WidgetTester tester) async {
  await signUp(tester);
  await tester.tap(find.byKey(const Key('demo-budget-save')));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('without a demo controller the app offers no demo', (
    tester,
  ) async {
    await pumpApp(tester);
    expect(find.byKey(const Key('open-demo')), findsNothing);
  });

  testWidgets('signing up asks for a budget prefilled with a typical one', (
    tester,
  ) async {
    await pumpDemoApp(tester, api: demoForecasts(), demoApi: FakeDemoApi());
    await signUp(tester);

    expect(find.text('Your monthly budget'), findsOneWidget);
    final rent = tester.widget<TextField>(
      find.byKey(const Key('demo-budget-Rent')),
    );
    expect(rent.controller!.text, '21300');
    expect(find.text('KSh 34,100'), findsOneWidget);
  });

  testWidgets('saving the budget opens Simulate, with no forecast yet', (
    tester,
  ) async {
    final api = demoForecasts();
    final demoApi = FakeDemoApi();
    await pumpDemoApp(tester, api: api, demoApi: demoApi);
    await signUpWithTypicalBudget(tester);

    expect(demoApi.calls, ['signup The Otienos', 'budget demo-1']);
    expect(find.byKey(const Key('demo-month')), findsOneWidget);
    expect(find.text('October 2026'), findsWidgets);
    expect(textContaining('0 of 3 months'), findsOneWidget);
    expect(api.forecastCalls, ['demo-1 2026-10']);
  });

  testWidgets('three simulated months make the forecast ready', (tester) async {
    final api = demoForecasts();
    final (controller, _) = await pumpDemoApp(
      tester,
      api: api,
      demoApi: FakeDemoApi(),
    );
    await signUpWithTypicalBudget(tester);

    await tester.tap(find.byKey(const Key('demo-simulate-1')));
    await tester.pumpAndSettle();
    expect(textContaining('1 of 3 months'), findsOneWidget);
    expect(controller.month, const YearMonth(2026, 11));
    expect(controller.dataLastMonth, october2026);

    await tester.tap(find.byKey(const Key('demo-simulate-3')));
    await tester.pumpAndSettle();
    expect(textContaining('is ready'), findsOneWidget);
    expect(api.forecastCalls.last, 'demo-1 2027-2');

    await tester.tap(find.byKey(const Key('demo-open-forecast')));
    await tester.pumpAndSettle();
    expect(find.text('Point estimate KSh 66,285'), findsOneWidget);
  });

  testWidgets('a spend is listed and the forecast reloads', (tester) async {
    final api = demoForecasts();
    final demoApi = FakeDemoApi();
    await pumpDemoApp(tester, api: api, demoApi: demoApi);
    await signUpWithTypicalBudget(tester);

    await tester.tap(find.byKey(const Key('demo-spend-category')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Groceries').last);
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('demo-spend-amount')), '45000');
    await tester.tap(find.byKey(const Key('demo-spend-add')));
    await tester.pumpAndSettle();

    expect(demoApi.calls.last, 'spend demo-1 Groceries 45000');
    expect(find.text('Added so far this month'), findsOneWidget);
    expect(find.text('KSh 45,000'), findsOneWidget);
    expect(api.forecastCalls, ['demo-1 2026-10', 'demo-1 2026-10']);
  });

  testWidgets('a wrong PIN is explained and nothing opens', (tester) async {
    final demoApi = FakeDemoApi();
    final (controller, demo) = await pumpDemoApp(
      tester,
      api: demoForecasts(),
      demoApi: demoApi,
    );
    await demoApi.signup('The Otienos', '1234');

    await tester.tap(find.byKey(const Key('open-demo')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Log in').first);
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('demo-name')), 'The Otienos');
    await tester.enterText(find.byKey(const Key('demo-pin')), '9999');
    await tester.tap(find.byKey(const Key('demo-submit')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('demo-error')), findsOneWidget);
    expect(textContaining('No demo household matches'), findsOneWidget);
    expect(demo.household, isNull);
    expect(controller.householdId, isNull);
  });

  testWidgets('logging in to a budgeted household goes straight to it', (
    tester,
  ) async {
    final demoApi = FakeDemoApi();
    final (controller, _) = await pumpDemoApp(
      tester,
      api: demoForecasts(),
      demoApi: demoApi,
    );
    final h = await demoApi.signup('The Otienos', '1234');
    await demoApi.saveBudget(h.userId, {'Rent': Decimal.fromInt(20000)});

    await tester.tap(find.byKey(const Key('open-demo')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Log in').first);
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('demo-name')), 'The Otienos');
    await tester.enterText(find.byKey(const Key('demo-pin')), '1234');
    await tester.tap(find.byKey(const Key('demo-submit')));
    await tester.pumpAndSettle();

    expect(controller.householdId, 'demo-1');
    expect(find.byKey(const Key('demo-month')), findsOneWidget);
  });

  testWidgets('logging out returns to household selection', (tester) async {
    final (controller, demo) = await pumpDemoApp(
      tester,
      api: demoForecasts(),
      demoApi: FakeDemoApi(),
    );
    await signUpWithTypicalBudget(tester);

    await tester.tap(find.byKey(const Key('demo-sign-out')));
    await tester.pumpAndSettle();

    expect(controller.householdId, isNull);
    expect(demo.household, isNull);
    expect(controller.dataLastMonth, september2026);
    expect(find.byKey(const Key('household-id')), findsOneWidget);
  });
}

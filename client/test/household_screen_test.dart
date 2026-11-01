// Household selection: wireframe 4.12a, FR-10, FR-16, IR-07.

import 'package:budget_forecast_client/presentation/app.dart';
import 'package:budget_forecast_client/presentation/widgets/common.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

void main() {
  testWidgets('starts idle, with the synthetic notice and the three fields', (
    tester,
  ) async {
    final controller = await pumpApp(tester);
    expect(controller.householdId, isNull);
    expect(find.text('Budget forecast'), findsOneWidget);
    expect(find.text(SyntheticNotice.text), findsOneWidget);
    expect(find.text('Household ID'), findsOneWidget);
    // Defaults to the month straight after the data ends.
    expect(find.text('October'), findsOneWidget);
    expect(find.text('2026'), findsOneWidget);
  });

  testWidgets('an empty household id is caught before any request', (
    tester,
  ) async {
    final api = FakeForecastApi();
    await pumpApp(tester, api: api);
    await tester.enterText(find.byKey(const Key('household-id')), '   ');
    await tester.tap(find.byKey(const Key('show-forecast')));
    await tester.pumpAndSettle();
    expect(find.text('Enter a household ID'), findsOneWidget);
    expect(api.forecastCalls, isEmpty);
  });

  testWidgets('shows the forecast for the chosen household, month and year', (
    tester,
  ) async {
    final api = FakeForecastApi();
    await pumpApp(tester, api: api);

    await tester.tap(find.byKey(const Key('month')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('July').last);
    await tester.pumpAndSettle();

    await showForecast(tester, ' h015 ');
    expect(api.forecastCalls, ['h015 2026-7']);
    expect(find.text('July 2026'), findsOneWidget);
  });

  testWidgets('keeps recently viewed households, and opens one on tap', (
    tester,
  ) async {
    final api = FakeForecastApi();
    final controller = await pumpApp(tester, api: api, recent: ['h007']);
    expect(find.text('Recent households'), findsOneWidget);

    await showForecast(tester, 'h015');
    controller.changeHousehold();
    await tester.pumpAndSettle();

    // Most recent first.
    final ids = tester
        .widgetList<ListTile>(find.byType(ListTile))
        .map((t) => (t.title as Text).data)
        .toList();
    expect(ids, ['h015', 'h007']);

    await tester.tap(find.byKey(const Key('recent-h007')));
    await tester.pumpAndSettle();
    expect(api.forecastCalls.last, 'h007 2026-10');
  });

  testWidgets('a build without FORECAST_API_URL says so instead of guessing', (
    tester,
  ) async {
    await tester.pumpWidget(const MissingConfigApp());
    expect(find.textContaining('FORECAST_API_URL'), findsOneWidget);
  });
}

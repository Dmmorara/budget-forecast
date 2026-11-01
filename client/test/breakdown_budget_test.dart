// Category breakdown (4.13c, FR-12) and budget vs forecast (4.13d, FR-13).

import 'dart:async';

import 'package:budget_forecast_client/presentation/widgets/common.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

Future<void> openBreakdown(WidgetTester tester) async {
  await tester.tap(find.text('Category breakdown'));
  await tester.pumpAndSettle();
}

Future<void> openBudget(WidgetTester tester) async {
  await tester.tap(find.text('Budget').last);
  await tester.pumpAndSettle();
}

double top(WidgetTester tester, String key) =>
    tester.getTopLeft(find.byKey(Key(key))).dy;

void main() {
  group('category breakdown', () {
    testWidgets('largest first, bars scaled to the largest, total = sum', (
      tester,
    ) async {
      await pumpApp(tester);
      await showForecast(tester, 'h015');
      await openBreakdown(tester);

      expect(find.text('Category breakdown'), findsWidgets);
      expect(find.text('h015  |  October 2026'), findsOneWidget);
      expect(find.text(SyntheticNotice.text), findsOneWidget);

      final order = [
        'Rent',
        'Groceries',
        'School Fees',
        'Transport',
        'Electronics Upgrade',
      ];
      for (var i = 1; i < order.length; i++) {
        expect(
          top(tester, 'category-${order[i - 1]}'),
          lessThan(top(tester, 'category-${order[i]}')),
        );
      }

      final bars = tester
          .widgetList<FractionBar>(find.byType(FractionBar))
          .map((b) => b.fraction)
          .toList();
      expect(bars.first, 1.0);
      expect(bars, orderedEquals([...bars]..sort((a, b) => b.compareTo(a))));

      // The same figure as the dashboard's point estimate.
      expect(
        tester.widget<Text>(find.byKey(const Key('breakdown-total'))).data,
        'KSh 66,285',
      );
    });

    testWidgets('back returns to the dashboard, not household selection', (
      tester,
    ) async {
      final controller = await pumpApp(tester);
      await showForecast(tester, 'h015');
      await openBreakdown(tester);
      await tester.tap(find.byKey(const Key('back')));
      await tester.pumpAndSettle();
      expect(controller.householdId, 'h015');
      expect(find.text('Likely to spend between'), findsOneWidget);
    });

    testWidgets('insufficient history explains rather than lists nothing', (
      tester,
    ) async {
      await pumpApp(
        tester,
        api: FakeForecastApi(forecast: (_, _, _) => insufficient),
      );
      await showForecast(tester, 'h999');
      // The dashboard has no link to follow; the breakdown is reached via
      // the controller's state, so check the dashboard explanation instead.
      expect(find.text('No forecast can be made yet'), findsOneWidget);
      expect(find.text('Category breakdown'), findsNothing);
    });
  });

  group('budget vs forecast', () {
    testWidgets('loads the budget only when opened', (tester) async {
      final api = FakeForecastApi();
      await pumpApp(tester, api: api);
      await showForecast(tester, 'h015');
      expect(api.budgetCalls, isEmpty);

      await openBudget(tester);
      expect(api.budgetCalls, ['h015']);
    });

    testWidgets('marks every category whose forecast exceeds the budget', (
      tester,
    ) async {
      await pumpApp(tester);
      await showForecast(tester, 'h015');
      await openBudget(tester);

      expect(find.text('Budget vs forecast'), findsOneWidget);
      expect(find.text(SyntheticNotice.text), findsOneWidget);
      expect(
        find.text('Forecast exceeds budget in 3 categories'),
        findsOneWidget,
      );
      // Groceries 13,627.60 > 12,900; Transport 7,722.80 > 7,166;
      // Electronics Upgrade 58.84 > a declared 0.
      for (final over in ['Groceries', 'Transport', 'Electronics Upgrade']) {
        expect(find.byKey(Key('over-$over')), findsOneWidget, reason: over);
      }
      for (final within in ['Rent', 'School Fees', 'Savings', 'Utilities']) {
        expect(find.byKey(Key('over-$within')), findsNothing, reason: within);
      }
      expect(
        find.text('Budget KSh 12,900  ·  Forecast KSh 13,628'),
        findsOneWidget,
      );
    });

    testWidgets('within budget everywhere says so', (tester) async {
      await pumpApp(
        tester,
        api: FakeForecastApi(
          budget: (_) => {
            ...h015Budget,
            'allocated': {
              for (final k in (h015October['breakdown']! as Map).keys)
                k: 99999.0,
            },
          },
        ),
      );
      await showForecast(tester, 'h015');
      await openBudget(tester);
      expect(
        find.text('Forecast is within budget in every category'),
        findsOneWidget,
      );
      expect(find.textContaining('over'), findsNothing);
    });

    testWidgets('an empty budget is "nothing to compare", not an error', (
      tester,
    ) async {
      await pumpApp(tester, api: FakeForecastApi(budget: (_) => emptyBudget));
      await showForecast(tester, 'h015');
      await openBudget(tester);
      expect(find.byKey(const Key('no-budget')), findsOneWidget);
      expect(
        find.textContaining('No declared budget for h015'),
        findsOneWidget,
      );
      expect(find.text('Retry'), findsNothing);
    });

    testWidgets('budget loading, then a network failure with retry', (
      tester,
    ) async {
      var reply = Completer<Object?>();
      final api = FakeForecastApi(budget: (_) => reply.future);
      await pumpApp(tester, api: api);
      await showForecast(tester, 'h015');
      await tester.tap(find.text('Budget').last);
      await tester.pump();
      await tester.pump();
      expect(find.text('Loading budget…'), findsOneWidget);

      reply.completeError(network);
      await tester.pumpAndSettle();
      expect(find.text('Cannot reach the service'), findsOneWidget);

      reply = Completer<Object?>()..complete(h015Budget);
      await tester.tap(find.text('Retry'));
      await tester.pumpAndSettle();
      expect(
        find.text('Forecast exceeds budget in 3 categories'),
        findsOneWidget,
      );
      expect(api.budgetCalls, ['h015', 'h015']);
    });

    testWidgets('a household with no history explains, before any budget', (
      tester,
    ) async {
      await pumpApp(
        tester,
        api: FakeForecastApi(
          forecast: (_, _, _) => insufficient,
          budget: (_) => emptyBudget,
        ),
      );
      await showForecast(tester, 'nobody');
      await openBudget(tester);
      expect(find.text('No forecast can be made yet'), findsOneWidget);
      expect(find.text('Retry'), findsNothing);
    });
  });
}

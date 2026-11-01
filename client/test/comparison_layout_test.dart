// Month comparison (4.14e, FR-14), the desktop layout (4.14f), and NFR-10's
// two widths. A RenderFlex overflow fails a widget test, so pumping each
// screen at 360 px and 1280 px is itself the overflow check.

import 'dart:async';

import 'package:budget_forecast_client/presentation/screens/comparison_screen.dart';
import 'package:budget_forecast_client/presentation/widgets/common.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

Future<void> openMonths(WidgetTester tester) async {
  await tester.tap(find.text('Months').last);
  await tester.pumpAndSettle();
}

Map<String, bool> dashedByMonth(WidgetTester tester) => {
  for (final bar in tester.widgetList<MonthBar>(find.byType(MonthBar)))
    bar.month.month.toString(): bar.month.afterDataEnd,
};

void main() {
  group('month comparison', () {
    testWidgets(
      'five consecutive months; only those past the data are dashed',
      (tester) async {
        final api = FakeForecastApi(forecast: (_, month, _) => forMonth(month));
        await pumpApp(tester, api: api);
        await showForecast(tester, 'h015');
        await openMonths(tester);

        expect(find.text('Compare months'), findsOneWidget);
        expect(find.text('h015  |  forecast by month'), findsOneWidget);
        expect(find.text(SyntheticNotice.text), findsOneWidget);
        expect(find.text('Dashed: after the data ends'), findsOneWidget);

        // Data ends September: October is the genuine forecast, November adds
        // nothing new and is dashed (wireframe 4.14e).
        expect(dashedByMonth(tester), {
          '2026-07': false,
          '2026-08': false,
          '2026-09': false,
          '2026-10': false,
          '2026-11': true,
        });
        expect(
          find.text('KSh 70,000  (KSh 60,000 – KSh 80,000)'),
          findsOneWidget,
        );
      },
    );

    testWidgets('without DATA_LAST_MONTH nothing is dashed, and it says why', (
      tester,
    ) async {
      await pumpApp(tester, dataLastMonth: null);
      await showForecast(tester, 'h015');
      await openMonths(tester);
      expect(dashedByMonth(tester).values, everyElement(isFalse));
      expect(find.textContaining('DATA_LAST_MONTH'), findsOneWidget);
    });

    testWidgets('months before the history starts show no forecast', (
      tester,
    ) async {
      await pumpApp(
        tester,
        api: FakeForecastApi(
          forecast: (_, month, _) => month < 9 ? insufficient : forMonth(month),
        ),
      );
      await showForecast(tester, 'h015');
      await openMonths(tester);
      expect(find.text('no forecast yet'), findsNWidgets(2));
    });

    testWidgets('loading, then an error with retry', (tester) async {
      var fail = true;
      final gate = Completer<void>();
      final api = FakeForecastApi(
        forecast: (_, month, _) async {
          if (month != 10) await gate.future;
          if (fail && month != 10) throw serverError;
          return forMonth(month);
        },
      );
      await pumpApp(tester, api: api);
      await showForecast(tester, 'h015');
      await tester.tap(find.text('Months').last);
      await tester.pump();
      await tester.pump();
      expect(find.text('Loading months…'), findsOneWidget);

      gate.complete();
      await tester.pumpAndSettle();
      expect(find.text('The service had a problem'), findsOneWidget);

      fail = false;
      await tester.tap(find.text('Retry'));
      await tester.pumpAndSettle();
      expect(find.byType(MonthBar), findsNWidgets(5));
    });
  });

  group('NFR-10 widths', () {
    for (final size in [const Size(360, 800), const Size(1280, 800)]) {
      testWidgets('every screen lays out at ${size.width.toInt()} px', (
        tester,
      ) async {
        await pumpApp(tester, size: size);
        expect(find.text('Show forecast'), findsOneWidget);
        await showForecast(tester, 'h015');

        final wide = size.width >= 900;
        if (wide) {
          for (final tab in ['side-budget', 'side-months', 'side-forecast']) {
            await tester.tap(find.byKey(Key(tab)));
            await tester.pumpAndSettle();
          }
        } else {
          await tester.scrollUntilVisible(find.text('Category breakdown'), 200);
          await tester.tap(find.text('Category breakdown'));
          await tester.pumpAndSettle();
          for (final tab in ['Budget', 'Months', 'Forecast']) {
            await tester.tap(find.text(tab).last);
            await tester.pumpAndSettle();
          }
        }
        expect(tester.takeException(), isNull);
      });
    }

    testWidgets('a long household id does not overflow at 360 px', (
      tester,
    ) async {
      await pumpApp(tester, size: const Size(360, 800));
      await showForecast(tester, 'household-with-a-very-long-identifier-0001');
      expect(tester.takeException(), isNull);
    });
  });

  group('desktop layout (4.14f)', () {
    testWidgets('side navigation, and breakdown beside budget', (tester) async {
      final api = FakeForecastApi();
      await pumpApp(tester, api: api, size: desktop);
      await showForecast(tester, 'h015');

      expect(find.byType(NavigationBar), findsNothing);
      expect(find.byKey(const Key('side-forecast')), findsOneWidget);
      expect(find.text('Household\nh015'), findsOneWidget);
      expect(
        find.text('October 2026: likely between KSh 55,658 and KSh 75,071'),
        findsOneWidget,
      );
      expect(find.text(SyntheticNotice.text), findsOneWidget);

      final breakdown = tester.getTopLeft(find.text('Category breakdown'));
      final budget = tester.getTopLeft(find.text('Budget vs forecast'));
      expect(breakdown.dy, budget.dy, reason: 'side by side');
      expect(breakdown.dx, lessThan(budget.dx));
      expect(api.budgetCalls, ['h015']);
      expect(
        find.text('Forecast exceeds budget in 3 categories'),
        findsOneWidget,
      );
    });

    testWidgets('change household from the side panel', (tester) async {
      final controller = await pumpApp(tester, size: desktop);
      await showForecast(tester, 'h015');
      await tester.tap(find.byKey(const Key('change-household')));
      await tester.pumpAndSettle();
      expect(controller.householdId, isNull);
    });

    testWidgets('a phone width uses the bottom navigation bar', (tester) async {
      await pumpApp(tester);
      await showForecast(tester, 'h015');
      expect(find.byType(NavigationBar), findsOneWidget);
      expect(find.byKey(const Key('side-forecast')), findsNothing);
    });
  });
}

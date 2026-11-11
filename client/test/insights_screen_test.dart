import 'package:budget_forecast_client/data/api_exception.dart';
import 'package:budget_forecast_client/data/insights.dart';
import 'package:budget_forecast_client/state/forecast_controller.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

Future<void> openInsights(WidgetTester tester) async {
  // The bottom bar's label is the last 'Insights' on screen.
  await tester.tap(find.text('Insights').last);
  await tester.pumpAndSettle();
}

/// h015's insights with the given month part and weekday marked as standing out.
Map<String, Object?> withStandingOut({int? part, int? weekday}) {
  final calendar = h015Insights['calendar']! as Map<String, Object?>;
  List<Object?> mark(String key, int? index) => [
    for (final (i, slot) in (calendar[key]! as List).indexed)
      {...(slot as Map).cast<String, Object?>(), 'standsOut': i == index},
  ];
  return {
    ...h015Insights,
    'calendar': {
      ...calendar,
      'monthParts': mark('monthParts', part),
      'weekdays': mark('weekdays', weekday),
    },
  };
}

void main() {
  group('what changed', () {
    testWidgets('largest change first, signed, against the named months', (
      tester,
    ) async {
      await pumpApp(tester);
      await showForecast(tester, 'h015');
      await openInsights(tester);

      expect(
        find.text(
          'The October 2026 forecast against a typical month of Jul–Sep 2026 '
          '(the median of the three)',
        ),
        findsOneWidget,
      );
      // Rent: 19,215 forecast against a typical 15,247.
      final rows = find.byWidgetPredicate(
        (w) =>
            w.key is ValueKey<String> &&
            (w.key! as ValueKey<String>).value.startsWith('change-'),
      );
      expect(tester.widget(rows.first).key, const ValueKey('change-Rent'));
      expect(find.text('+KSh 3,968'), findsWidgets);
      expect(find.byKey(const Key('total-change')), findsOneWidget);
      // Six of eleven until asked for the rest.
      expect(rows, findsNWidgets(6));
      await tester.tap(find.byKey(const Key('show-all-changes')));
      await tester.pumpAndSettle();
      expect(rows, findsNWidgets(11));
    });

    testWidgets('the dashboard previews the three largest and links here', (
      tester,
    ) async {
      final api = FakeForecastApi();
      await pumpApp(tester, api: api);
      await showForecast(tester, 'h015');

      final preview = find.byKey(const Key('what-changed'));
      expect(preview, findsOneWidget);
      expect(
        find.descendant(
          of: preview,
          matching: find.byWidgetPredicate(
            (w) =>
                w.key is ValueKey<String> &&
                (w.key! as ValueKey<String>).value.startsWith('change-'),
          ),
        ),
        findsNWidgets(3),
      );
      await tester.tap(
        find.descendant(of: preview, matching: find.text('See all')),
      );
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('spending-calendar')), findsOneWidget);
      // One request serves both the preview and the screen.
      expect(api.insightsCalls, ['h015 2026-10']);
    });

    testWidgets('a failed insights request leaves the forecast untouched', (
      tester,
    ) async {
      await pumpApp(
        tester,
        api: FakeForecastApi(insights: (_, _, _) => throw serverError),
      );
      await showForecast(tester, 'h015');
      expect(find.text('KSh 55,658 and KSh 75,071'), findsOneWidget);
      expect(find.byKey(const Key('what-changed')), findsNothing);
      expect(find.text('Retry'), findsNothing);
    });
  });

  group('spending calendar', () {
    testWidgets('an even spread is reported as even, not as a habit', (
      tester,
    ) async {
      await pumpApp(tester);
      await showForecast(tester, 'h015');
      await openInsights(tester);

      expect(
        find.text('Spending is spread evenly through the month and the week.'),
        findsOneWidget,
      );
      expect(find.text('Spread evenly'), findsOneWidget);
      expect(find.text('Days 1–7'), findsOneWidget);
      expect(find.text('Days 22–end'), findsOneWidget);
      expect(find.text('Sunday'), findsOneWidget);
    });

    testWidgets('a slot the service marks as standing out is named', (
      tester,
    ) async {
      await pumpApp(
        tester,
        api: FakeForecastApi(insights: (_, _, _) => withStandingOut(part: 0)),
      );
      await showForecast(tester, 'h015');
      await openInsights(tester);

      expect(
        find.text('Days 1–7 takes more than an even share of spending.'),
        findsOneWidget,
      );
      expect(find.text('Days 1–7'), findsWidgets);
    });
  });

  group('discretionary share', () {
    testWidgets('none in twelve months says so', (tester) async {
      await pumpApp(tester);
      await showForecast(tester, 'h015');
      await openInsights(tester);

      expect(find.byKey(const Key('no-discretionary')), findsOneWidget);
      expect(find.text('None'), findsOneWidget);
    });

    testWidgets('a month with spending is listed with its categories', (
      tester,
    ) async {
      await pumpApp(
        tester,
        api: FakeForecastApi(
          insights: (_, _, _) => withDiscretionaryIn('2026-07', 1500),
        ),
      );
      await showForecast(tester, 'h015');
      await openInsights(tester);

      expect(find.byKey(const Key('discretionary-2026-07')), findsOneWidget);
      expect(find.text('Cash Advance'), findsOneWidget);
      expect(find.text('1 of 12 months'), findsOneWidget);
      expect(find.byKey(const Key('no-discretionary')), findsNothing);
    });
  });

  group('states', () {
    testWidgets('too little history explains, as the forecast does', (
      tester,
    ) async {
      await pumpApp(
        tester,
        api: FakeForecastApi(
          forecast: (_, _, _) => insufficient,
          insights: (_, _, _) => insufficientInsights,
        ),
      );
      await showForecast(tester, 'nobody');
      await openInsights(tester);
      expect(find.text('No forecast can be made yet'), findsOneWidget);
      expect(find.byKey(const Key('spending-calendar')), findsNothing);
    });

    testWidgets('an error offers a retry that reloads', (tester) async {
      var fail = true;
      final api = FakeForecastApi(
        insights: (_, _, _) => fail ? throw network : h015Insights,
      );
      await pumpApp(tester, api: api);
      await showForecast(tester, 'h015');
      await openInsights(tester);

      expect(find.text('Cannot reach the service'), findsOneWidget);
      fail = false;
      await tester.tap(find.text('Retry'));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('spending-calendar')), findsOneWidget);
    });

    testWidgets('changing month reloads the insights for that month', (
      tester,
    ) async {
      final api = FakeForecastApi();
      final controller = await pumpApp(tester, api: api);
      await showForecast(tester, 'h015');
      await openInsights(tester);
      await tester.tap(find.byKey(const Key('next-month')));
      await tester.pumpAndSettle();

      expect(api.insightsCalls, ['h015 2026-10', 'h015 2026-11']);
      expect(controller.insights.state, LoadState.loaded);
    });

    for (final size in [const Size(360, 800), desktop]) {
      testWidgets('lays out at ${size.width.toInt()} px', (tester) async {
        await pumpApp(
          tester,
          size: size,
          api: FakeForecastApi(
            insights: (_, _, _) => withDiscretionaryIn('2026-07', 1500),
          ),
        );
        await showForecast(tester, 'h015');
        if (size.width >= 900) {
          await tester.tap(find.byKey(const Key('side-insights')));
        } else {
          await tester.tap(find.text('Insights').last);
        }
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
        expect(find.byKey(const Key('what-changed')), findsOneWidget);
      });
    }
  });

  group('parsing', () {
    test('the captured response parses', () {
      final result = InsightsResult.fromJson(h015Insights);
      expect(result.historyMonths, 18);
      expect(result.usual!.months.length, 3);
      expect(result.calendar!.monthParts.map((p) => p.label), [
        'Days 1–7',
        'Days 8–14',
        'Days 15–21',
        'Days 22–end',
      ]);
      expect(result.calendar!.weekdays.length, 7);
      expect(result.discretionary!.monthsWithAny, 0);
    });

    test('a share outside 0..1 is an error, never a bar', () {
      final calendar = h015Insights['calendar']! as Map<String, Object?>;
      final parts = [...calendar['monthParts']! as List];
      parts[0] = {...(parts[0] as Map).cast<String, Object?>(), 'share': 1.5};
      expect(
        () => InsightsResult.fromJson({
          ...h015Insights,
          'calendar': {...calendar, 'monthParts': parts},
        }),
        throwsA(isA<ApiException>()),
      );
    });

    test('insufficient history parses to empty sections', () {
      final result = InsightsResult.fromJson(insufficientInsights);
      expect(result.isInsufficient, isTrue);
      expect(result.calendar, isNull);
    });
  });
}

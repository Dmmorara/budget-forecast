// Forecast dashboard: wireframe 4.12b, FR-06, FR-11, FR-15, FR-16, IR-04,
// IR-05, and every state of Figure 4.8.

import 'dart:async';

import 'package:budget_forecast_client/presentation/widgets/common.dart';
import 'package:budget_forecast_client/state/forecast_controller.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

void main() {
  testWidgets('loaded: leads with the range, then the band, then the point', (
    tester,
  ) async {
    final controller = await pumpApp(tester);
    await showForecast(tester, 'h015');

    expect(controller.state, LoadState.loaded);
    expect(find.text('h015'), findsOneWidget);
    expect(find.text('October 2026'), findsOneWidget);
    expect(find.text(SyntheticNotice.text), findsOneWidget);
    expect(find.text('Likely to spend between'), findsOneWidget);
    expect(find.text('KSh 55,658 and KSh 75,071'), findsOneWidget);
    expect(find.byKey(const Key('range-band')), findsOneWidget);
    expect(find.text('Point estimate KSh 66,285'), findsOneWidget);
    expect(find.text('Confidence 0.78'), findsOneWidget);
    expect(find.text('Risk flag: none'), findsOneWidget);
    expect(find.byKey(const Key('risk-notice')), findsNothing);

    // The range is read before the single number.
    final range = tester.getTopLeft(find.byKey(const Key('range-sentence'))).dy;
    final band = tester.getTopLeft(find.byKey(const Key('range-band'))).dy;
    final point = tester.getTopLeft(find.byKey(const Key('point-estimate'))).dy;
    expect(range < band && band < point, isTrue);
  });

  testWidgets('loading shows a spinner, then the waking message after 5 s', (
    tester,
  ) async {
    final reply = Completer<Object?>();
    await pumpApp(
      tester,
      api: FakeForecastApi(forecast: (_, _, _) => reply.future),
    );
    await tester.enterText(find.byKey(const Key('household-id')), 'h015');
    await tester.tap(find.byKey(const Key('show-forecast')));
    await tester.pump();

    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(find.text('Loading forecast…'), findsOneWidget);
    expect(find.text(SyntheticNotice.text), findsOneWidget);

    await tester.pump(const Duration(milliseconds: 4900));
    expect(find.text(LoadingView.wakingText), findsNothing);
    await tester.pump(const Duration(milliseconds: 200));
    expect(find.text(LoadingView.wakingText), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    // The service wakes up: the forecast replaces the message.
    reply.complete(h015October);
    await tester.pumpAndSettle();
    expect(find.text(LoadingView.wakingText), findsNothing);
    expect(find.text('KSh 55,658 and KSh 75,071'), findsOneWidget);
  });

  testWidgets('insufficient history is an explanation, not an error', (
    tester,
  ) async {
    final controller = await pumpApp(
      tester,
      api: FakeForecastApi(forecast: (_, _, _) => insufficient),
    );
    await showForecast(tester, 'h999');

    expect(controller.state, LoadState.loaded);
    expect(find.text('No forecast can be made yet'), findsOneWidget);
    expect(find.textContaining('fewer than three months'), findsOneWidget);
    expect(find.text('Retry'), findsNothing);
    expect(find.textContaining('KSh'), findsNothing);
    expect(find.text(SyntheticNotice.text), findsOneWidget);
  });

  testWidgets('volatile shows the forecast with a caution notice', (
    tester,
  ) async {
    await pumpApp(
      tester,
      api: FakeForecastApi(forecast: (_, _, _) => withFlag('volatile')),
    );
    await showForecast(tester, 'h015');
    expect(find.text('Risk flag: volatile'), findsOneWidget);
    expect(find.textContaining('Caution'), findsOneWidget);
    expect(find.text('KSh 55,658 and KSh 75,071'), findsOneWidget);
  });

  testWidgets('overspend_risk (reserved) shows an overspend notice', (
    tester,
  ) async {
    await pumpApp(
      tester,
      api: FakeForecastApi(forecast: (_, _, _) => withFlag('overspend_risk')),
    );
    await showForecast(tester, 'h015');
    expect(find.text('Risk flag: overspend risk'), findsOneWidget);
    expect(find.textContaining('Overspend notice'), findsOneWidget);
  });

  testWidgets('an unknown risk flag is an error, never displayed (IR-05)', (
    tester,
  ) async {
    final controller = await pumpApp(
      tester,
      api: FakeForecastApi(forecast: (_, _, _) => withFlag('mild_concern')),
    );
    await showForecast(tester, 'h015');
    expect(controller.state, LoadState.error);
    expect(find.text('The service had a problem'), findsOneWidget);
    expect(find.textContaining('Risk flag'), findsNothing);
    expect(find.text('Retry'), findsOneWidget);
  });

  testWidgets('invalid request: names the field, offers retry and correction', (
    tester,
  ) async {
    final controller = await pumpApp(
      tester,
      api: FakeForecastApi(forecast: (_, _, _) => throw invalid),
    );
    await showForecast(tester, 'h015');

    expect(controller.state, LoadState.error);
    expect(find.text('The request was rejected'), findsOneWidget);
    expect(find.textContaining('"month"'), findsOneWidget);
    expect(find.text('Retry'), findsOneWidget);

    await tester.tap(find.text('Change household'));
    await tester.pumpAndSettle();
    expect(controller.state, LoadState.idle);
    expect(find.text('Show forecast'), findsOneWidget);
  });

  testWidgets('network failure, then retry succeeds', (tester) async {
    var fail = true;
    final api = FakeForecastApi(
      forecast: (_, _, _) {
        if (fail) throw network;
        return h015October;
      },
    );
    final controller = await pumpApp(tester, api: api);
    await showForecast(tester, 'h015');

    expect(controller.state, LoadState.error);
    expect(find.text('Cannot reach the service'), findsOneWidget);
    expect(find.text('Change household'), findsNothing);

    fail = false;
    await tester.tap(find.text('Retry'));
    await tester.pumpAndSettle();
    expect(controller.state, LoadState.loaded);
    expect(find.text('KSh 55,658 and KSh 75,071'), findsOneWidget);
    expect(api.forecastCalls, ['h015 2026-10', 'h015 2026-10']);
  });

  testWidgets('timeout and server errors each have their own message', (
    tester,
  ) async {
    Object error = timeout;
    await pumpApp(
      tester,
      api: FakeForecastApi(forecast: (_, _, _) => throw error),
    );
    await showForecast(tester, 'h015');
    expect(find.text('The service did not answer in time'), findsOneWidget);

    error = serverError;
    await tester.tap(find.text('Retry'));
    await tester.pumpAndSettle();
    expect(find.text('The service had a problem'), findsOneWidget);
    expect(find.textContaining('HTTP 503'), findsOneWidget);
  });

  testWidgets('steps months without returning to household selection', (
    tester,
  ) async {
    final api = FakeForecastApi(forecast: (_, month, _) => forMonth(month));
    await pumpApp(tester, api: api);
    await showForecast(tester, 'h015');
    expect(find.text('Point estimate KSh 70,000'), findsOneWidget);

    await tester.tap(find.byKey(const Key('next-month')));
    await tester.pumpAndSettle();
    expect(find.text('November 2026'), findsOneWidget);
    expect(find.text('Point estimate KSh 71,000'), findsOneWidget);

    await tester.tap(find.byKey(const Key('previous-month')));
    await tester.tap(find.byKey(const Key('previous-month')));
    await tester.pumpAndSettle();
    expect(find.text('September 2026'), findsOneWidget);
    expect(api.forecastCalls, [
      'h015 2026-10',
      'h015 2026-11',
      'h015 2026-10',
      'h015 2026-9',
    ]);
  });

  testWidgets('a slow earlier month cannot overwrite a later one', (
    tester,
  ) async {
    final october = Completer<Object?>();
    final api = FakeForecastApi(
      forecast: (_, month, _) => month == 10 ? october.future : forMonth(month),
    );
    await pumpApp(tester, api: api);
    await tester.enterText(find.byKey(const Key('household-id')), 'h015');
    await tester.tap(find.byKey(const Key('show-forecast')));
    await tester.pump();

    await tester.tap(find.byKey(const Key('next-month')));
    await tester.pumpAndSettle();
    october.complete(h015October);
    await tester.pumpAndSettle();

    expect(find.text('November 2026'), findsOneWidget);
    expect(find.text('Point estimate KSh 71,000'), findsOneWidget);
  });

  testWidgets('back changes household: Loaded -> Idle', (tester) async {
    final controller = await pumpApp(tester);
    await showForecast(tester, 'h015');
    await tester.tap(find.byKey(const Key('back')));
    await tester.pumpAndSettle();
    expect(controller.householdId, isNull);
    expect(controller.state, LoadState.idle);
    expect(find.text('Show forecast'), findsOneWidget);
  });
}

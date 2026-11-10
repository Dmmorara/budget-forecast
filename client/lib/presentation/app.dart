library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/forecast_controller.dart';
import 'screens/household_screen.dart';
import 'shell.dart';
import 'theme.dart';

/// Idle shows household selection; any selected household shows the shell.
/// Switching on the controller rather than pushing routes keeps Figure 4.8's
/// "change household -> Idle" a single state change.
class BudgetForecastApp extends StatelessWidget {
  const BudgetForecastApp({super.key, required this.controller});

  final ForecastController controller;

  static ThemeData theme() => appTheme();

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider.value(
      value: controller,
      child: MaterialApp(
        title: 'Budget forecast',
        theme: theme(),
        debugShowCheckedModeBanner: false,
        home: Consumer<ForecastController>(
          builder: (context, c, _) => c.householdId == null
              ? const HouseholdScreen()
              : const HomeShell(),
        ),
      ),
    );
  }
}

/// Shown instead of the app when the build has no service address (IR-01).
class MissingConfigApp extends StatelessWidget {
  const MissingConfigApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Budget forecast',
    theme: BudgetForecastApp.theme(),
    debugShowCheckedModeBanner: false,
    home: const Scaffold(
      body: Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Text(
            'This build has no service address.\n\n'
            'Rebuild with --dart-define=FORECAST_API_URL=<service URL>, '
            'for example http://localhost:8000.',
            textAlign: TextAlign.center,
          ),
        ),
      ),
    ),
  );
}

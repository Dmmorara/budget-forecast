import 'package:flutter/material.dart';

import 'config.dart';
import 'data/forecast_api.dart';
import 'data/recent_households.dart';
import 'presentation/app.dart';
import 'state/demo_controller.dart';
import 'state/forecast_controller.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  final config = AppConfig.fromEnvironment();
  final apiUrl = config.apiUrl;
  if (apiUrl == null) {
    runApp(const MissingConfigApp());
    return;
  }

  final client = ForecastApiClient(baseUrl: apiUrl);
  final controller = ForecastController(
    api: client,
    recent: PreferencesRecentHouseholds(),
    dataLastMonth: config.dataLastMonth,
  )..loadRecent();
  final demo = DemoController(api: client, forecast: controller);
  runApp(BudgetForecastApp(controller: controller, demo: demo));
}

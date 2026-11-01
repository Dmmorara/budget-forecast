import 'package:flutter/material.dart';

import 'config.dart';
import 'data/forecast_api.dart';
import 'data/recent_households.dart';
import 'presentation/app.dart';
import 'state/forecast_controller.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  final config = AppConfig.fromEnvironment();
  final apiUrl = config.apiUrl;
  if (apiUrl == null) {
    runApp(const MissingConfigApp());
    return;
  }

  final controller = ForecastController(
    api: ForecastApiClient(baseUrl: apiUrl),
    recent: PreferencesRecentHouseholds(),
    dataLastMonth: config.dataLastMonth,
  )..loadRecent();
  runApp(BudgetForecastApp(controller: controller));
}

/// Build-time configuration, supplied with --dart-define.
///
///   flutter run -d chrome --web-port=5000 \
///     --dart-define=FORECAST_API_URL=http://localhost:8000 \
///     --dart-define=DATA_LAST_MONTH=2026-09
library;

import 'data/models.dart';

class AppConfig {
  const AppConfig({required this.apiUrl, required this.dataLastMonth});

  /// IR-01: the service's base URL. Never hard-coded: an address baked into
  /// the source would point every build at one environment, and the deployed
  /// Render URL is not known until the service is deployed.
  final Uri? apiUrl;

  /// The last month the service holds spending data for.
  ///
  /// LIMITATION: no endpoint exposes this. The service knows it (it is the
  /// latest month in the extract it loaded), but neither POST /forecast nor
  /// GET /budget returns it, so the client is told at build time and must be
  /// rebuilt if the extract changes. A stale value draws the wrong months
  /// dashed in the month comparison (FR-14); it never changes a figure.
  /// The fix belongs in the service: a field such as `dataLastMonth` on an
  /// existing response, agreed with the consuming teams first.
  final YearMonth? dataLastMonth;

  static AppConfig fromEnvironment() => AppConfig(
    apiUrl: parseApiUrl(const String.fromEnvironment('FORECAST_API_URL')),
    dataLastMonth: YearMonth.tryParse(
      const String.fromEnvironment('DATA_LAST_MONTH'),
    ),
  );

  /// Null unless the value is an absolute http(s) URL.
  static Uri? parseApiUrl(String raw) {
    final trimmed = raw.trim();
    if (trimmed.isEmpty) return null;
    final uri = Uri.tryParse(
      trimmed.endsWith('/')
          ? trimmed.substring(0, trimmed.length - 1)
          : trimmed,
    );
    if (uri == null || !uri.hasAuthority) return null;
    if (uri.scheme != 'http' && uri.scheme != 'https') return null;
    return uri;
  }
}

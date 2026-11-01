/// The only code in the client that speaks HTTP (§4.4.1).
library;

import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'api_exception.dart';
import 'models.dart';

/// What the state layer depends on. Tests supply a fake; nothing in the
/// widget tests makes a network call.
abstract interface class ForecastApi {
  Future<ForecastResult> getForecast(String userId, int month, int year);
  Future<BudgetResult> getBudget(String userId);
}

class ForecastApiClient implements ForecastApi {
  ForecastApiClient({
    required this.baseUrl,
    http.Client? client,
    this.timeout = defaultTimeout,
  }) : _client = client ?? http.Client();

  /// IR-04. Render's free plan sleeps after ~15 minutes idle and the first
  /// request then takes about 50 seconds, so the limit sits above that.
  static const defaultTimeout = Duration(seconds: 60);

  final Uri baseUrl;
  final Duration timeout;
  final http.Client _client;

  Uri _endpoint(String path, [Map<String, String>? query]) =>
      baseUrl.replace(path: '${baseUrl.path}$path', queryParameters: query);

  @override
  Future<ForecastResult> getForecast(String userId, int month, int year) async {
    final body = await _send(
      () => _client.post(
        _endpoint('/forecast'),
        headers: const {'Content-Type': 'application/json'},
        body: jsonEncode({'userId': userId, 'month': month, 'year': year}),
      ),
    );
    return ForecastResult.fromJson(body);
  }

  @override
  Future<BudgetResult> getBudget(String userId) async {
    // An unknown household is a 200 with an empty `allocated`, never a 404.
    final body = await _send(
      () => _client.get(_endpoint('/budget', {'userId': userId})),
    );
    return BudgetResult.fromJson(body);
  }

  Future<Object?> _send(Future<http.Response> Function() request) async {
    final http.Response response;
    try {
      response = await request().timeout(timeout);
    } on TimeoutException {
      throw ApiException(
        ApiErrorKind.timeout,
        'The service did not answer within ${timeout.inSeconds} seconds.',
      );
    } on http.ClientException catch (error) {
      throw ApiException(
        ApiErrorKind.network,
        'Could not reach the service (${error.message}).',
      );
    }

    final status = response.statusCode;
    if (status == 422) throw _validationError(response.body);
    if (status >= 500) {
      throw ApiException(
        ApiErrorKind.server,
        'The service failed with HTTP $status.',
      );
    }
    if (status != 200) {
      throw ApiException(
        ApiErrorKind.server,
        'Unexpected HTTP $status from the service.',
      );
    }
    try {
      return jsonDecode(response.body);
    } on FormatException {
      throw ApiException.invalidResponse('body is not JSON');
    }
  }

  /// FastAPI's 422 body: {"detail": [{"loc": ["body", "month"], "msg": ...}]}.
  /// Reports the first rejected field so the screen can name it (Table 4.9).
  static ApiException _validationError(String body) {
    String? field;
    String? detail;
    try {
      final errors = (jsonDecode(body) as Map<String, Object?>)['detail'];
      if (errors is List && errors.isNotEmpty && errors.first is Map) {
        final first = errors.first as Map;
        final loc = first['loc'];
        if (loc is List && loc.isNotEmpty) field = loc.last.toString();
        detail = first['msg']?.toString();
      }
    } catch (_) {
      // An unreadable 422 is still a validation error; just less specific.
    }
    final where = field == null ? 'A field' : '"$field"';
    return ApiException(
      ApiErrorKind.validation,
      '$where was rejected by the service${detail == null ? '' : ': $detail'}.',
      field: field,
    );
  }
}

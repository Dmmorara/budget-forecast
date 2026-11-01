/// The one error type the data layer raises (Figure 4.7), so a screen can
/// show the right message for each failure without knowing about HTTP.
library;

enum ApiErrorKind {
  /// No answer within the 60-second limit (IR-04).
  timeout,

  /// The request never reached the service: offline, DNS, refused, or — in a
  /// browser — blocked by CORS, which is indistinguishable from the client.
  network,

  /// HTTP 422: a field is missing, empty or out of range.
  validation,

  /// HTTP 5xx, any other unexpected status, or a body outside the contract,
  /// including a riskFlag outside the closed set (IR-05).
  server,
}

class ApiException implements Exception {
  const ApiException(this.kind, this.message, {this.field});

  factory ApiException.invalidResponse(String detail) => ApiException(
    ApiErrorKind.server,
    'The service sent a response this app does not understand ($detail).',
  );

  final ApiErrorKind kind;
  final String message;

  /// For a 422, the request field the service rejected, e.g. "month".
  final String? field;

  @override
  String toString() => 'ApiException(${kind.name}): $message';
}

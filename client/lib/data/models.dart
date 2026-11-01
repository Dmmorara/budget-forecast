/// Typed results of the budget-forecast service (Figure 4.7).
///
/// Money is Decimal throughout (IR-06). The service sends amounts as JSON
/// numbers, which `jsonDecode` turns into doubles before this code sees them;
/// [moneyFromJson] converts each one back through its shortest round-trip
/// string, which recovers the exact decimal the service wrote (it rounds to
/// two places). After that point no amount is ever held or summed as a double.
library;

import 'package:decimal/decimal.dart';

import 'api_exception.dart';

/// IR-05: the closed set of risk flags. Anything else is an error.
enum RiskFlag {
  insufficientHistory('insufficient_history'),
  volatile('volatile'),

  /// Reserved: Table 4.9 says the shipped forecaster never emits it. Handled
  /// so that a future service that does emit it is shown correctly.
  overspendRisk('overspend_risk');

  const RiskFlag(this.wire);
  final String wire;

  /// Null for JSON null. Throws for any value outside the closed set, so an
  /// unexpected flag reaches the user as an error rather than as text.
  static RiskFlag? fromJson(Object? value) {
    if (value == null) return null;
    for (final flag in values) {
      if (flag.wire == value) return flag;
    }
    throw ApiException.invalidResponse('unexpected riskFlag "$value"');
  }
}

Decimal moneyFromJson(Object? value, String field) {
  if (value is num) return Decimal.parse(value.toString());
  if (value is String) {
    final parsed = Decimal.tryParse(value);
    if (parsed != null) return parsed;
  }
  throw ApiException.invalidResponse('"$field" is not an amount: $value');
}

Decimal? optionalMoneyFromJson(Object? value, String field) =>
    value == null ? null : moneyFromJson(value, field);

Map<String, Decimal> moneyMapFromJson(Object? value, String field) {
  if (value is! Map) {
    throw ApiException.invalidResponse('"$field" is not an object');
  }
  return {
    for (final entry in value.entries)
      entry.key.toString(): moneyFromJson(entry.value, '$field.${entry.key}'),
  };
}

Map<String, Object?> _object(Object? json) {
  if (json is Map<String, Object?>) return json;
  throw ApiException.invalidResponse('response is not a JSON object');
}

class ForecastResult {
  const ForecastResult({
    required this.estimatedTotal,
    required this.breakdown,
    required this.confidence,
    required this.riskFlag,
    required this.low,
    required this.high,
    required this.isSynthetic,
    required this.method,
  });

  final Decimal estimatedTotal;
  final Map<String, Decimal> breakdown;

  /// A score in 0..1, not money, so a double is correct here.
  final double confidence;
  final RiskFlag? riskFlag;

  /// estimatedTotalLow / estimatedTotalHigh. Null for insufficient_history.
  final Decimal? low;
  final Decimal? high;
  final bool isSynthetic;
  final String method;

  bool get hasRange => low != null && high != null;

  /// Categories largest first (FR-12).
  List<MapEntry<String, Decimal>> get breakdownLargestFirst =>
      breakdown.entries.toList()..sort((a, b) => b.value.compareTo(a.value));

  factory ForecastResult.fromJson(Object? json) {
    final map = _object(json);
    final confidence = map['confidence'];
    if (confidence is! num) {
      throw ApiException.invalidResponse('"confidence" is not a number');
    }
    return ForecastResult(
      estimatedTotal: moneyFromJson(map['estimatedTotal'], 'estimatedTotal'),
      breakdown: moneyMapFromJson(map['breakdown'], 'breakdown'),
      confidence: confidence.toDouble(),
      riskFlag: RiskFlag.fromJson(map['riskFlag']),
      low: optionalMoneyFromJson(map['estimatedTotalLow'], 'estimatedTotalLow'),
      high: optionalMoneyFromJson(
        map['estimatedTotalHigh'],
        'estimatedTotalHigh',
      ),
      isSynthetic: map['isSynthetic'] != false,
      method: map['method']?.toString() ?? '',
    );
  }
}

class BudgetResult {
  const BudgetResult({
    required this.userId,
    required this.allocated,
    required this.isSynthetic,
  });

  final String userId;

  /// Empty for an unknown household, or one that declared no budget. The
  /// service answers both with a 200: there is simply nothing to show.
  final Map<String, Decimal> allocated;
  final bool isSynthetic;

  bool get isEmpty => allocated.isEmpty;

  factory BudgetResult.fromJson(Object? json) {
    final map = _object(json);
    return BudgetResult(
      userId: map['userId']?.toString() ?? '',
      allocated: moneyMapFromJson(map['allocated'], 'allocated'),
      isSynthetic: map['isSynthetic'] != false,
    );
  }
}

/// A calendar month. Comparable, and steps across year boundaries.
class YearMonth implements Comparable<YearMonth> {
  const YearMonth(this.year, this.month) : assert(month >= 1 && month <= 12);

  final int year;
  final int month;

  YearMonth plus(int months) {
    final index = year * 12 + (month - 1) + months;
    return YearMonth(index ~/ 12, index % 12 + 1);
  }

  /// "2026-09" or "2026-9". Null for anything else, including empty.
  static YearMonth? tryParse(String raw) {
    final match = RegExp(r'^(\d{4})-(\d{1,2})$').firstMatch(raw.trim());
    if (match == null) return null;
    final month = int.parse(match.group(2)!);
    if (month < 1 || month > 12) return null;
    return YearMonth(int.parse(match.group(1)!), month);
  }

  @override
  int compareTo(YearMonth other) =>
      (year * 12 + month).compareTo(other.year * 12 + other.month);

  bool isAfter(YearMonth other) => compareTo(other) > 0;

  @override
  bool operator ==(Object other) =>
      other is YearMonth && other.year == year && other.month == month;

  @override
  int get hashCode => Object.hash(year, month);

  @override
  String toString() => '$year-${month.toString().padLeft(2, '0')}';
}

/// One month of the comparison screen (FR-14).
class MonthForecast {
  const MonthForecast({
    required this.month,
    required this.result,
    required this.afterDataEnd,
  });

  final YearMonth month;
  final ForecastResult result;

  /// Drawn dashed. See ForecastController.isAfterDataEnd for the rule.
  final bool afterDataEnd;
}

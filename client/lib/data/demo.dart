/// Demo households, for presentations: the /demo endpoints (app/demo.py).
///
/// A presenter signs a household up with a name and a PIN, declares a
/// budget, and builds its history a month at a time. The "login" is not
/// authentication, and every figure is synthetic. Once signed in, a demo
/// household is forecast through the same [ForecastApi] as any other.
library;

import 'package:decimal/decimal.dart';

import 'api_exception.dart';
import 'models.dart';

abstract interface class DemoApi {
  Future<DemoCategories> getDemoCategories();
  Future<DemoHousehold> signup(String name, String pin);
  Future<DemoHousehold> login(String name, String pin);
  Future<DemoHousehold> saveBudget(
    String userId,
    Map<String, Decimal> allocated,
  );
  Future<DemoHousehold> addSpend(
    String userId,
    String category,
    Decimal amount,
  );
  Future<DemoHousehold> simulate(String userId, int months);
}

/// Months of history the service needs before it forecasts (FR-06).
const monthsForForecast = 3;

class DemoHousehold {
  const DemoHousehold({
    required this.userId,
    required this.name,
    required this.month,
    required this.historyMonths,
    required this.budget,
    required this.spentThisMonth,
  });

  final String userId;
  final String name;

  /// The month in progress: the one forecast, and the one a spend lands in.
  final YearMonth month;

  /// Months completed before [month].
  final int historyMonths;
  final Map<String, Decimal> budget;
  final Map<String, Decimal> spentThisMonth;

  /// The last month with complete history, which the comparison screen
  /// treats as the end of the data.
  YearMonth get lastCompleteMonth => month.plus(-1);

  bool get hasBudget => budget.values.any((v) => v > Decimal.zero);

  factory DemoHousehold.fromJson(Object? json) {
    if (json is! Map<String, Object?>) {
      throw ApiException.invalidResponse('household is not a JSON object');
    }
    final month = json['month'];
    final year = json['year'];
    final history = json['historyMonths'];
    if (month is! int || year is! int || history is! int) {
      throw ApiException.invalidResponse('household has no month in progress');
    }
    return DemoHousehold(
      userId: json['userId']?.toString() ?? '',
      name: json['name']?.toString() ?? '',
      month: YearMonth(year, month),
      historyMonths: history,
      budget: moneyMapFromJson(json['budget'], 'budget'),
      spentThisMonth: moneyMapFromJson(
        json['spentThisMonth'],
        'spentThisMonth',
      ),
    );
  }
}

class DemoCategories {
  const DemoCategories({required this.categories, required this.typical});

  final List<String> categories;

  /// A typical sandbox budget per category, to prefill the budget form.
  final Map<String, Decimal> typical;

  factory DemoCategories.fromJson(Object? json) {
    if (json is! Map<String, Object?> || json['categories'] is! List) {
      throw ApiException.invalidResponse('categories are not a list');
    }
    return DemoCategories(
      categories: [for (final c in json['categories']! as List) c.toString()],
      typical: moneyMapFromJson(json['typical'], 'typical'),
    );
  }
}

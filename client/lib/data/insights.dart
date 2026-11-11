/// Typed result of GET /insights: usual spend, the spending calendar and the
/// discretionary trend, all from months before the selected one.
///
/// Money is Decimal, as everywhere else (IR-06). Shares are fractions of a
/// total, not money, so they stay doubles.
library;

import 'package:decimal/decimal.dart';

import 'api_exception.dart';
import 'models.dart';

class InsightsResult {
  const InsightsResult({
    required this.userId,
    required this.month,
    required this.historyMonths,
    required this.usual,
    required this.calendar,
    required this.discretionary,
    required this.isSynthetic,
  });

  final String userId;
  final YearMonth month;

  /// Months with recorded spending before [month].
  final int historyMonths;

  /// All three null when there are fewer than three months of history, or the
  /// household is unknown: the service's insufficient-history answer.
  final UsualSpend? usual;
  final SpendingCalendar? calendar;
  final DiscretionaryTrend? discretionary;
  final bool isSynthetic;

  bool get isInsufficient => usual == null;

  factory InsightsResult.fromJson(Object? json) {
    final map = _object(json, 'response');
    final month = map['month'], year = map['year'];
    if (month is! int || year is! int || month < 1 || month > 12) {
      throw ApiException.invalidResponse('"month"/"year" are not a month');
    }
    return InsightsResult(
      userId: map['userId']?.toString() ?? '',
      month: YearMonth(year, month),
      historyMonths: _int(map['historyMonths'], 'historyMonths'),
      usual: map['usual'] == null ? null : UsualSpend.fromJson(map['usual']),
      calendar: map['calendar'] == null
          ? null
          : SpendingCalendar.fromJson(map['calendar']),
      discretionary: map['discretionary'] == null
          ? null
          : DiscretionaryTrend.fromJson(map['discretionary']),
      isSynthetic: map['isSynthetic'] != false,
    );
  }
}

class UsualSpend {
  const UsualSpend({
    required this.months,
    required this.total,
    required this.breakdown,
  });

  /// The months averaged, oldest first.
  final List<YearMonth> months;
  final Decimal total;
  final Map<String, Decimal> breakdown;

  factory UsualSpend.fromJson(Object? json) {
    final map = _object(json, 'usual');
    return UsualSpend(
      months: _months(map['months'], 'usual.months'),
      total: moneyFromJson(map['total'], 'usual.total'),
      breakdown: moneyMapFromJson(map['breakdown'], 'usual.breakdown'),
    );
  }
}

/// One stretch of the calendar: part of the month, or a day of the week.
class CalendarSlot {
  const CalendarSlot({
    required this.label,
    required this.shortLabel,
    required this.share,
    required this.evenShare,
    required this.standsOut,
    required this.averageAmount,
  });

  /// "Days 1–7" / "Monday".
  final String label;

  /// "1–7" / "Mon", under a column.
  final String shortLabel;
  final double share;

  /// The share an even spread over the calendar days would give.
  final double evenShare;

  /// The service's test that this is a pattern, not month-to-month noise.
  final bool standsOut;
  final Decimal averageAmount;
}

class SpendingCalendar {
  const SpendingCalendar({
    required this.months,
    required this.monthParts,
    required this.weekdays,
  });

  final List<YearMonth> months;
  final List<CalendarSlot> monthParts;
  final List<CalendarSlot> weekdays;

  static const _weekdayNames = [
    'Monday',
    'Tuesday',
    'Wednesday',
    'Thursday',
    'Friday',
    'Saturday',
    'Sunday',
  ];

  factory SpendingCalendar.fromJson(Object? json) {
    final map = _object(json, 'calendar');
    CalendarSlot slot(Object? raw, String field, String label, String short) {
      final m = _object(raw, field);
      return CalendarSlot(
        label: label,
        shortLabel: short,
        share: _fraction(m['share'], '$field.share'),
        evenShare: _fraction(m['evenShare'], '$field.evenShare'),
        standsOut: m['standsOut'] == true,
        averageAmount: moneyFromJson(
          m['averageAmount'],
          '$field.averageAmount',
        ),
      );
    }

    return SpendingCalendar(
      months: _months(map['months'], 'calendar.months'),
      monthParts: [
        for (final (i, raw) in _list(map['monthParts'], 'monthParts').indexed)
          () {
            final m = _object(raw, 'monthParts[$i]');
            final first = _int(m['firstDay'], 'firstDay');
            final last = _int(m['lastDay'], 'lastDay');
            final range = last >= 28 ? '$first–end' : '$first–$last';
            return slot(raw, 'monthParts[$i]', 'Days $range', range);
          }(),
      ],
      weekdays: [
        for (final (i, raw) in _list(map['weekdays'], 'weekdays').indexed)
          () {
            final day = _int(
              _object(raw, 'weekdays[$i]')['weekday'],
              'weekday',
            );
            if (day < 1 || day > 7) {
              throw ApiException.invalidResponse('weekday $day');
            }
            final name = _weekdayNames[day - 1];
            return slot(raw, 'weekdays[$i]', name, name.substring(0, 3));
          }(),
      ],
    );
  }
}

class DiscretionaryMonth {
  const DiscretionaryMonth({
    required this.month,
    required this.total,
    required this.amount,
    required this.share,
    required this.byCategory,
  });

  final YearMonth month;
  final Decimal total;
  final Decimal amount;
  final double share;
  final Map<String, Decimal> byCategory;
}

class DiscretionaryTrend {
  const DiscretionaryTrend({required this.categories, required this.months});

  final List<String> categories;
  final List<DiscretionaryMonth> months;

  int get monthsWithAny => months.where((m) => m.amount > Decimal.zero).length;

  factory DiscretionaryTrend.fromJson(Object? json) {
    final map = _object(json, 'discretionary');
    return DiscretionaryTrend(
      categories: [
        for (final c in _list(map['categories'], 'categories')) c.toString(),
      ],
      months: [
        for (final (i, raw) in _list(map['months'], 'months').indexed)
          () {
            final m = _object(raw, 'months[$i]');
            return DiscretionaryMonth(
              month: _month(m['month'], 'months[$i].month'),
              total: moneyFromJson(m['total'], 'months[$i].total'),
              amount: moneyFromJson(m['amount'], 'months[$i].amount'),
              share: _fraction(m['share'], 'months[$i].share'),
              byCategory: moneyMapFromJson(
                m['byCategory'],
                'months[$i].byCategory',
              ),
            );
          }(),
      ],
    );
  }
}

Map<String, Object?> _object(Object? json, String field) {
  if (json is Map<String, Object?>) return json;
  throw ApiException.invalidResponse('"$field" is not an object');
}

List<Object?> _list(Object? json, String field) {
  if (json is List) return json;
  throw ApiException.invalidResponse('"$field" is not a list');
}

int _int(Object? value, String field) {
  if (value is int) return value;
  throw ApiException.invalidResponse('"$field" is not a whole number');
}

double _fraction(Object? value, String field) {
  if (value is num && value >= 0 && value <= 1) return value.toDouble();
  throw ApiException.invalidResponse('"$field" is not a share: $value');
}

YearMonth _month(Object? value, String field) {
  final parsed = value is String ? YearMonth.tryParse(value) : null;
  if (parsed != null) return parsed;
  throw ApiException.invalidResponse('"$field" is not a month: $value');
}

List<YearMonth> _months(Object? value, String field) => [
  for (final (i, m) in _list(value, field).indexed) _month(m, '$field[$i]'),
];

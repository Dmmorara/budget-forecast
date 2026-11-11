/// NFR-10: Kenyan shillings with thousands separators.
library;

import 'package:decimal/decimal.dart';
import 'package:intl/intl.dart';

import '../data/models.dart';

/// "KSh 66,285". Rounded to whole shillings for display only: the value
/// itself stays an exact Decimal, and the grouping is done on the integer's
/// digits so no amount passes through a double on the way to the screen.
String kes(Decimal amount) {
  final whole = amount.round().toBigInt();
  final digits = whole.abs().toString();
  final grouped = StringBuffer();
  for (var i = 0; i < digits.length; i++) {
    if (i > 0 && (digits.length - i) % 3 == 0) grouped.write(',');
    grouped.write(digits[i]);
  }
  return 'KSh ${whole.isNegative ? '-' : ''}$grouped';
}

/// Width of a bar relative to the largest, for layout only. A fraction of
/// the screen is not money, so converting the ratio to a double is correct.
double fractionOf(Decimal value, Decimal largest) {
  if (largest <= Decimal.zero || value <= Decimal.zero) return 0;
  final ratio = (value / largest).toDouble();
  return ratio.clamp(0.0, 1.0);
}

Decimal sum(Iterable<Decimal> values) =>
    values.fold(Decimal.zero, (total, value) => total + value);

String monthLabel(YearMonth month) =>
    DateFormat('MMMM yyyy').format(DateTime(month.year, month.month));

String monthShort(YearMonth month) =>
    DateFormat('MMM').format(DateTime(month.year, month.month));

String monthName(int month) => DateFormat('MMMM').format(DateTime(2000, month));

/// "32%": [value]'s share of [total], whole percent, for display only.
String percentOf(Decimal value, Decimal total) =>
    '${(fractionOf(value, total) * 100).round()}%';

/// "109K": an amount in whole thousands, for a label on a chart mark where
/// the full figure is shown alongside it.
String thousands(Decimal amount) {
  final k = (amount / Decimal.fromInt(1000)).toDecimal(
    scaleOnInfinitePrecision: 0,
  );
  return '${k.round()}K';
}

/// "+KSh 6,000" / "−KSh 1,200" / "no change", for a difference.
String signedKes(Decimal change) {
  final whole = change.round();
  if (whole == Decimal.zero) return 'no change';
  return '${whole > Decimal.zero ? '+' : '\u2212'}${kes(whole.abs())}';
}

/// "38%": a share already expressed as a fraction.
String percent(double fraction) => '${(fraction * 100).round()}%';

/// "Jul–Sep 2026" or "Oct 2025–Sep 2026": a span of months.
String monthSpan(YearMonth first, YearMonth last) {
  final end = '${monthShort(last)} ${last.year}';
  if (first == last) return end;
  final start = first.year == last.year
      ? monthShort(first)
      : '${monthShort(first)} ${first.year}';
  return '$start–$end';
}

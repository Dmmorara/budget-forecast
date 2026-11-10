/// Month comparison — wireframe 4.14e, FR-14.
///
/// Bars are point forecasts and whiskers the likely range; the selected month
/// is the dark bar, labelled with its value. Months after the
/// end of the available data are drawn dashed; which month that is comes from
/// --dart-define=DATA_LAST_MONTH, because no endpoint exposes it (see
/// AppConfig.dataLastMonth for the limitation).
library;

import 'package:decimal/decimal.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../data/models.dart';
import '../../state/forecast_controller.dart';
import '../format.dart';
import '../theme.dart';
import '../widgets/common.dart';

class ComparisonScreen extends StatefulWidget {
  const ComparisonScreen({super.key});

  @override
  State<ComparisonScreen> createState() => _ComparisonScreenState();
}

class _ComparisonScreenState extends State<ComparisonScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) context.read<ForecastController>().loadComparison();
    });
  }

  @override
  Widget build(BuildContext context) {
    final controller = context.watch<ForecastController>();
    final comparison = controller.comparison;
    const muted = Palette.muted;

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
      children: [
        ContextLine('${controller.householdId}  |  forecast by month'),
        const SyntheticNotice(),
        const SizedBox(height: 12),
        const SizedBox(height: 4),
        const Text('Bars: point forecast', style: TextStyle(color: muted)),
        const Text('Whiskers: likely range', style: TextStyle(color: muted)),
        const SizedBox(height: 14),
        switch (comparison.state) {
          LoadState.idle || LoadState.loading => LoadingView(
            waking: comparison.waking,
            what: 'months',
          ),
          LoadState.error => ErrorView(
            error: comparison.error!,
            onRetry: () => controller.loadComparison(force: true),
            onChangeHousehold: controller.changeHousehold,
          ),
          LoadState.loaded => _Loaded(
            months: comparison.value!,
            selected: controller.month,
            dataEndKnown: controller.dataLastMonth != null,
          ),
        },
      ],
    );
  }
}

class _Loaded extends StatelessWidget {
  const _Loaded({
    required this.months,
    required this.selected,
    required this.dataEndKnown,
  });
  final List<MonthForecast> months;
  final YearMonth? selected;
  final bool dataEndKnown;

  @override
  Widget build(BuildContext context) {
    final scale = months
        .map((m) => m.result.high ?? m.result.estimatedTotal)
        .fold(Decimal.zero, (a, b) => a > b ? a : b);
    const muted = Palette.muted;
    final textTheme = Theme.of(context).textTheme;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SectionCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              SizedBox(
                height: 260,
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    for (final m in months)
                      Expanded(
                        child: MonthBar(
                          month: m,
                          scale: scale,
                          selected: m.month == selected,
                        ),
                      ),
                  ],
                ),
              ),
              const SizedBox(height: 12),
              Text(
                dataEndKnown
                    ? 'Dashed: after the data ends'
                    : 'The end of the data was not configured for this build '
                          '(DATA_LAST_MONTH), so no month is marked.',
                style: const TextStyle(
                  fontStyle: FontStyle.italic,
                  color: muted,
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),
        // The table view: every value the chart shows, in words.
        SectionCard(
          padding: const EdgeInsets.fromLTRB(20, 10, 20, 10),
          child: Column(
            children: [
              for (final (i, m) in months.indexed)
                Container(
                  key: Key('month-row-${m.month}'),
                  padding: const EdgeInsets.symmetric(vertical: 12),
                  decoration: BoxDecoration(
                    border: i == months.length - 1
                        ? null
                        : const Border(
                            bottom: BorderSide(color: Palette.outline),
                          ),
                  ),
                  child: Row(
                    children: [
                      SizedBox(
                        width: 130,
                        child: Text(
                          monthLabel(m.month),
                          style: m.month == selected
                              ? textTheme.titleSmall
                              : null,
                        ),
                      ),
                      Expanded(
                        child: Text(
                          _describe(m),
                          textAlign: TextAlign.right,
                          style: m.afterDataEnd
                              ? const TextStyle(
                                  fontStyle: FontStyle.italic,
                                  color: muted,
                                )
                              : null,
                        ),
                      ),
                    ],
                  ),
                ),
            ],
          ),
        ),
      ],
    );
  }

  static String _describe(MonthForecast m) {
    final r = m.result;
    if (r.riskFlag == RiskFlag.insufficientHistory) return 'no forecast yet';
    final range = r.hasRange ? '  (${kes(r.low!)} – ${kes(r.high!)})' : '';
    return '${kes(r.estimatedTotal)}$range';
  }
}

/// One month's bar and whisker. Public so tests can read [MonthForecast.afterDataEnd].
class MonthBar extends StatelessWidget {
  const MonthBar({
    super.key,
    required this.month,
    required this.scale,
    this.selected = false,
  });

  final MonthForecast month;
  final Decimal scale;

  /// The month the rest of the app is showing: drawn dark and labelled.
  final bool selected;

  @override
  Widget build(BuildContext context) {
    final r = month.result;
    final insufficient = r.riskFlag == RiskFlag.insufficientHistory;
    final description =
        '${monthLabel(month.month)}: '
        '${insufficient ? 'no forecast' : kes(r.estimatedTotal)}'
        '${r.hasRange && !insufficient ? ', likely ${kes(r.low!)} to ${kes(r.high!)}' : ''}'
        '${month.afterDataEnd ? ', after the data ends' : ''}';

    return Tooltip(
      message: description,
      excludeFromSemantics: true,
      child: Semantics(
        label: description,
        excludeSemantics: true,
        child: Column(
          children: [
            Expanded(
              child: insufficient
                  ? const Center(child: Text('–'))
                  : CustomPaint(
                      size: Size.infinite,
                      painter: _BarPainter(
                        point: fractionOf(r.estimatedTotal, scale),
                        low: r.low == null ? null : fractionOf(r.low!, scale),
                        high: r.high == null
                            ? null
                            : fractionOf(r.high!, scale),
                        dashed: month.afterDataEnd,
                        fill: selected ? Palette.forest : Palette.sage,
                        line: Palette.ink,
                        label: selected ? thousands(r.estimatedTotal) : null,
                        labelStyle: Theme.of(context).textTheme.labelSmall
                            ?.copyWith(
                              color: Colors.white,
                              fontWeight: FontWeight.w600,
                            ),
                      ),
                    ),
            ),
            const SizedBox(height: 8),
            Text(
              monthShort(month.month),
              style: TextStyle(
                color: selected ? Palette.ink : Palette.muted,
                fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _BarPainter extends CustomPainter {
  _BarPainter({
    required this.point,
    required this.low,
    required this.high,
    required this.dashed,
    required this.fill,
    required this.line,
    this.label,
    this.labelStyle,
  });

  final double point;
  final double? low;
  final double? high;
  final bool dashed;
  final Color fill;
  final Color line;

  /// Drawn in a forest bubble above the whisker, for the selected month.
  final String? label;
  final TextStyle? labelStyle;

  /// Head room above the tallest whisker for [label].
  static const _top = 30.0;

  @override
  void paint(Canvas canvas, Size size) {
    // At most 24 px: the band's leftover is air, not a wider bar.
    final barWidth = (size.width * 0.5).clamp(8.0, 24.0);
    final left = (size.width - barWidth) / 2;
    final plot = size.height - _top;
    double y(double fraction) => _top + plot * (1 - fraction);

    // Rounded 4 px at the data end, square at the baseline.
    final bar = RRect.fromRectAndCorners(
      Rect.fromLTRB(left, y(point), left + barWidth, size.height),
      topLeft: const Radius.circular(4),
      topRight: const Radius.circular(4),
    );

    if (dashed) {
      _dashedRect(
        canvas,
        bar.outerRect,
        Paint()
          ..color = fill == Palette.forest ? Palette.forest : line
          ..strokeWidth = 1.5
          ..style = PaintingStyle.stroke,
      );
    } else {
      canvas.drawRRect(bar, Paint()..color = fill);
    }

    var labelAnchor = y(point);
    if (low != null && high != null) {
      final whisker = Paint()
        ..color = line
        ..strokeWidth = 2
        ..strokeCap = StrokeCap.round;
      final cx = size.width / 2;
      final cap = barWidth * 0.4;
      canvas
        ..drawLine(Offset(cx, y(low!)), Offset(cx, y(high!)), whisker)
        ..drawLine(
          Offset(cx - cap, y(high!)),
          Offset(cx + cap, y(high!)),
          whisker,
        )
        ..drawLine(
          Offset(cx - cap, y(low!)),
          Offset(cx + cap, y(low!)),
          whisker,
        );
      labelAnchor = y(high!);
    }

    if (label != null) {
      final text = TextPainter(
        text: TextSpan(text: label, style: labelStyle),
        textDirection: TextDirection.ltr,
      )..layout();
      final w = text.width + 14;
      // Only drawn if it fits the column; the table below always has it.
      if (w <= size.width) {
        final h = text.height + 6;
        final top = (labelAnchor - h - 6).clamp(0.0, size.height - h);
        final rect = RRect.fromRectAndRadius(
          Rect.fromLTWH((size.width - w) / 2, top, w, h),
          const Radius.circular(8),
        );
        canvas.drawRRect(rect, Paint()..color = Palette.forest);
        text.paint(canvas, Offset(rect.left + 7, rect.top + 3));
      }
    }
  }

  void _dashedRect(Canvas canvas, Rect rect, Paint paint) {
    const dash = 5.0, gap = 4.0;
    void dashedLine(Offset a, Offset b) {
      final length = (b - a).distance;
      final step = (b - a) / length;
      for (var d = 0.0; d < length; d += dash + gap) {
        final end = (d + dash).clamp(0.0, length);
        canvas.drawLine(a + step * d, a + step * end, paint);
      }
    }

    dashedLine(rect.topLeft, rect.topRight);
    dashedLine(rect.topRight, rect.bottomRight);
    dashedLine(rect.bottomRight, rect.bottomLeft);
    dashedLine(rect.bottomLeft, rect.topLeft);
  }

  @override
  bool shouldRepaint(_BarPainter old) =>
      old.point != point ||
      old.low != low ||
      old.high != high ||
      old.dashed != dashed ||
      old.fill != fill ||
      old.line != line ||
      old.label != label ||
      old.labelStyle != labelStyle;
}

/// Month comparison — wireframe 4.14e, FR-14.
///
/// Bars are point forecasts and whiskers the likely range. Months after the
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
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        ContextLine('${controller.householdId}  |  forecast by month'),
        const SyntheticNotice(),
        const SizedBox(height: 12),
        Text('Bars: point forecast', style: TextStyle(color: muted)),
        Text('Whiskers: likely range', style: TextStyle(color: muted)),
        const SizedBox(height: 16),
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
            dataEndKnown: controller.dataLastMonth != null,
          ),
        },
      ],
    );
  }
}

class _Loaded extends StatelessWidget {
  const _Loaded({required this.months, required this.dataEndKnown});
  final List<MonthForecast> months;
  final bool dataEndKnown;

  @override
  Widget build(BuildContext context) {
    final scale = months
        .map((m) => m.result.high ?? m.result.estimatedTotal)
        .fold(Decimal.zero, (a, b) => a > b ? a : b);
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SizedBox(
          height: 240,
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              for (final m in months)
                Expanded(
                  child: MonthBar(month: m, scale: scale),
                ),
            ],
          ),
        ),
        const SizedBox(height: 8),
        Text(
          dataEndKnown
              ? 'Dashed: after the data ends'
              : 'The end of the data was not configured for this build '
                    '(DATA_LAST_MONTH), so no month is marked.',
          style: TextStyle(fontStyle: FontStyle.italic, color: muted),
        ),
        const SizedBox(height: 16),
        for (final m in months)
          Padding(
            key: Key('month-row-${m.month}'),
            padding: const EdgeInsets.only(bottom: 6),
            child: Row(
              children: [
                SizedBox(width: 130, child: Text(monthLabel(m.month))),
                Expanded(
                  child: Text(
                    _describe(m),
                    textAlign: TextAlign.right,
                    style: m.afterDataEnd
                        ? TextStyle(fontStyle: FontStyle.italic, color: muted)
                        : null,
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
  const MonthBar({super.key, required this.month, required this.scale});

  final MonthForecast month;
  final Decimal scale;

  @override
  Widget build(BuildContext context) {
    final r = month.result;
    final scheme = Theme.of(context).colorScheme;
    final insufficient = r.riskFlag == RiskFlag.insufficientHistory;

    return Semantics(
      label:
          '${monthLabel(month.month)}: '
          '${insufficient ? 'no forecast' : kes(r.estimatedTotal)}'
          '${month.afterDataEnd ? ', after the data ends' : ''}',
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
                      high: r.high == null ? null : fractionOf(r.high!, scale),
                      dashed: month.afterDataEnd,
                      fill: scheme.surfaceContainerHighest,
                      line: scheme.onSurface,
                    ),
                  ),
          ),
          const SizedBox(height: 6),
          Text(monthShort(month.month)),
        ],
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
  });

  final double point;
  final double? low;
  final double? high;
  final bool dashed;
  final Color fill;
  final Color line;

  @override
  void paint(Canvas canvas, Size size) {
    final barWidth = (size.width * 0.5).clamp(8.0, 48.0);
    final left = (size.width - barWidth) / 2;
    double y(double fraction) => size.height * (1 - fraction);

    final bar = Rect.fromLTRB(left, y(point), left + barWidth, size.height);
    final stroke = Paint()
      ..color = line
      ..strokeWidth = 1.5
      ..style = PaintingStyle.stroke;

    if (dashed) {
      _dashedRect(canvas, bar, stroke);
    } else {
      canvas.drawRect(bar, Paint()..color = fill);
      canvas.drawRect(bar, stroke);
    }

    if (low != null && high != null) {
      final cx = size.width / 2;
      final cap = barWidth * 0.35;
      canvas
        ..drawLine(Offset(cx, y(low!)), Offset(cx, y(high!)), stroke)
        ..drawLine(
          Offset(cx - cap, y(high!)),
          Offset(cx + cap, y(high!)),
          stroke,
        )
        ..drawLine(
          Offset(cx - cap, y(low!)),
          Offset(cx + cap, y(low!)),
          stroke,
        );
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
      old.line != line;
}

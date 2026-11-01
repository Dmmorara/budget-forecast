/// Forecast dashboard — wireframe 4.12b (phone) and 4.14f (desktop), FR-11.
///
/// Leads with a sentence stating the RANGE and a band placing the point
/// estimate inside it, so the uncertainty is read before the single number.
library;

import 'package:decimal/decimal.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../data/models.dart';
import '../../state/forecast_controller.dart';
import '../format.dart';
import '../widgets/common.dart';
import 'breakdown_screen.dart';
import 'budget_screen.dart';

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({
    super.key,
    required this.wide,
    required this.onOpenBreakdown,
    required this.onOpenBudget,
    required this.onOpenMonths,
  });

  /// Desktop layout: breakdown and budget panels side by side beneath the band.
  final bool wide;
  final VoidCallback onOpenBreakdown;
  final VoidCallback onOpenBudget;
  final VoidCallback onOpenMonths;

  @override
  Widget build(BuildContext context) {
    final controller = context.watch<ForecastController>();
    final month = controller.month!;

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        _MonthStepper(month: month),
        const SizedBox(height: 12),
        const SyntheticNotice(),
        const SizedBox(height: 16),
        ForecastStatus(
          builder: (result) => [
            _RangeSummary(result: result, month: month, wide: wide),
            const SizedBox(height: 24),
            if (wide)
              _WidePanels(result: result)
            else ...[
              _LinkTile(label: 'Category breakdown', onTap: onOpenBreakdown),
              _LinkTile(label: 'Budget vs forecast', onTap: onOpenBudget),
              _LinkTile(label: 'Compare months', onTap: onOpenMonths),
            ],
          ],
        ),
      ],
    );
  }
}

/// Renders the forecast request's state: loading (and waking), error with
/// retry, insufficient history as an explanation, or [builder]'s content.
/// Shared by every screen that shows the selected month's forecast.
class ForecastStatus extends StatelessWidget {
  const ForecastStatus({super.key, required this.builder});

  final List<Widget> Function(ForecastResult result) builder;

  @override
  Widget build(BuildContext context) {
    final controller = context.watch<ForecastController>();
    final forecast = controller.forecast;

    final Widget content = switch (forecast.state) {
      LoadState.idle ||
      LoadState.loading => LoadingView(waking: forecast.waking),
      LoadState.error => ErrorView(
        error: forecast.error!,
        onRetry: controller.loadForecast,
        onChangeHousehold: controller.changeHousehold,
      ),
      LoadState.loaded
          when forecast.value!.riskFlag == RiskFlag.insufficientHistory =>
        InsufficientHistoryView(
          householdId: controller.householdId!,
          month: controller.month!,
        ),
      LoadState.loaded => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: builder(forecast.value!),
      ),
    };
    return content;
  }
}

class _MonthStepper extends StatelessWidget {
  const _MonthStepper({required this.month});
  final YearMonth month;

  @override
  Widget build(BuildContext context) {
    final controller = context.read<ForecastController>();
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        IconButton(
          key: const Key('previous-month'),
          tooltip: 'Previous month',
          icon: const Icon(Icons.chevron_left),
          onPressed: () => controller.changeMonth(-1),
        ),
        Flexible(
          child: Text(
            monthLabel(month),
            key: const Key('selected-month'),
            style: Theme.of(context).textTheme.titleLarge,
            textAlign: TextAlign.center,
          ),
        ),
        IconButton(
          key: const Key('next-month'),
          tooltip: 'Next month',
          icon: const Icon(Icons.chevron_right),
          onPressed: () => controller.changeMonth(1),
        ),
      ],
    );
  }
}

class _RangeSummary extends StatelessWidget {
  const _RangeSummary({
    required this.result,
    required this.month,
    required this.wide,
  });

  final ForecastResult result;
  final YearMonth month;
  final bool wide;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final low = result.low;
    final high = result.high;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (low != null && high != null) ...[
          if (wide)
            Text(
              '${monthLabel(month)}: likely between ${kes(low)} and ${kes(high)}',
              key: const Key('range-sentence'),
              style: textTheme.titleLarge?.copyWith(
                fontWeight: FontWeight.bold,
              ),
            )
          else ...[
            Text('Likely to spend between', style: textTheme.titleMedium),
            const SizedBox(height: 4),
            Text(
              '${kes(low)} and ${kes(high)}',
              key: const Key('range-sentence'),
              style: textTheme.headlineSmall?.copyWith(
                fontWeight: FontWeight.bold,
              ),
            ),
          ],
          const SizedBox(height: 16),
          RangeBand(low: low, high: high, point: result.estimatedTotal),
          const SizedBox(height: 10),
        ],
        Text(
          'Point estimate ${kes(result.estimatedTotal)}',
          key: const Key('point-estimate'),
          style: textTheme.titleMedium?.copyWith(
            color: Theme.of(context).colorScheme.onSurfaceVariant,
          ),
        ),
        const SizedBox(height: 16),
        Wrap(
          spacing: 12,
          runSpacing: 12,
          children: [
            _Chip('Confidence ${result.confidence.toStringAsFixed(2)}'),
            _Chip('Risk flag: ${riskLabel(result.riskFlag)}'),
          ],
        ),
        if (riskNotice(result.riskFlag) case final String notice) ...[
          const SizedBox(height: 12),
          Container(
            key: const Key('risk-notice'),
            width: double.infinity,
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Theme.of(context).colorScheme.tertiaryContainer,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(notice),
          ),
        ],
      ],
    );
  }
}

String riskLabel(RiskFlag? flag) => switch (flag) {
  null => 'none',
  RiskFlag.insufficientHistory => 'insufficient history',
  RiskFlag.volatile => 'volatile',
  RiskFlag.overspendRisk => 'overspend risk',
};

/// Table 4.9's client behaviour for the flags shown alongside a forecast.
String? riskNotice(RiskFlag? flag) => switch (flag) {
  RiskFlag.volatile =>
    'Caution: this household\'s spending varies a lot '
        'from month to month, so the likely range is wide. Plan against the '
        'upper end.',
  RiskFlag.overspendRisk =>
    'Overspend notice: this forecast is '
        'materially above the household\'s declared budget.',
  _ => null,
};

/// The likely range as a shaded band on a wider track, with the point
/// estimate marked inside it (wireframe 4.12b).
class RangeBand extends StatelessWidget {
  const RangeBand({
    super.key,
    required this.low,
    required this.high,
    required this.point,
  });

  final Decimal low;
  final Decimal high;
  final Decimal point;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    // The track extends half the range's width either side, so the band sits
    // in the middle and its width reads as uncertainty, not as a scale from 0.
    final half = ((high - low) / Decimal.fromInt(2)).toDecimal(
      scaleOnInfinitePrecision: 2,
    );
    var start = low - half;
    if (start < Decimal.zero) start = Decimal.zero;
    final end = high + half;
    final span = end - start;
    double at(Decimal v) => fractionOf(v - start, span);

    return Semantics(
      label:
          'Likely range ${kes(low)} to ${kes(high)}, '
          'point estimate ${kes(point)}',
      excludeSemantics: true,
      child: SizedBox(
        height: 44,
        child: LayoutBuilder(
          builder: (context, constraints) {
            final w = constraints.maxWidth;
            return Stack(
              children: [
                Positioned(
                  left: 0,
                  right: 0,
                  top: 8,
                  height: 28,
                  child: Container(
                    decoration: BoxDecoration(
                      color: scheme.surfaceContainerHighest,
                      border: Border.all(color: scheme.outlineVariant),
                    ),
                  ),
                ),
                Positioned(
                  left: w * at(low),
                  width: w * (at(high) - at(low)),
                  top: 8,
                  height: 28,
                  child: Container(
                    key: const Key('range-band'),
                    decoration: BoxDecoration(
                      color: scheme.primaryContainer,
                      border: Border.all(color: scheme.outline),
                    ),
                  ),
                ),
                Positioned(
                  left: (w * at(point) - 2).clamp(0.0, w - 4),
                  width: 4,
                  top: 0,
                  bottom: 0,
                  child: Container(color: scheme.onSurface),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _Chip extends StatelessWidget {
  const _Chip(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
    decoration: BoxDecoration(
      color: Theme.of(context).colorScheme.surfaceContainerHighest,
      border: Border.all(color: Theme.of(context).colorScheme.outline),
      borderRadius: BorderRadius.circular(8),
    ),
    child: Text(text),
  );
}

class _LinkTile extends StatelessWidget {
  const _LinkTile({required this.label, required this.onTap});
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 10),
    child: OutlinedButton(
      onPressed: onTap,
      style: OutlinedButton.styleFrom(
        minimumSize: const Size.fromHeight(52),
        alignment: Alignment.centerLeft,
      ),
      child: Row(
        children: [
          Expanded(child: Text(label)),
          const Icon(Icons.chevron_right),
        ],
      ),
    ),
  );
}

/// Wireframe 4.14f: breakdown and budget comparison side by side.
class _WidePanels extends StatefulWidget {
  const _WidePanels({required this.result});
  final ForecastResult result;

  @override
  State<_WidePanels> createState() => _WidePanelsState();
}

class _WidePanelsState extends State<_WidePanels> {
  @override
  void initState() {
    super.initState();
    // The phone layout loads the budget when its screen is opened; here the
    // panel is on screen at once, so it is loaded at once.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) context.read<ForecastController>().loadBudget();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: _Panel(
            title: 'Category breakdown',
            child: BreakdownList(result: widget.result),
          ),
        ),
        const SizedBox(width: 20),
        const Expanded(
          child: _Panel(title: 'Budget vs forecast', child: BudgetComparison()),
        ),
      ],
    );
  }
}

class _Panel extends StatelessWidget {
  const _Panel({required this.title, required this.child});
  final String title;
  final Widget child;

  @override
  Widget build(BuildContext context) => Card(
    margin: EdgeInsets.zero,
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 12),
          child,
        ],
      ),
    ),
  );
}

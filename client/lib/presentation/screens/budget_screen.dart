/// Budget vs forecast — wireframe 4.13d, FR-13.
///
/// The declared budget comes from GET /budget; the comparison is computed in
/// the client (ForecastController.categoriesOverBudget). The service does not
/// flag overspending, and its reserved overspend_risk flag is never emitted.
library;

import 'package:decimal/decimal.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../state/forecast_controller.dart';
import '../format.dart';
import '../widgets/common.dart';
import 'dashboard_screen.dart';

class BudgetScreen extends StatefulWidget {
  const BudgetScreen({super.key});

  @override
  State<BudgetScreen> createState() => _BudgetScreenState();
}

class _BudgetScreenState extends State<BudgetScreen> {
  @override
  void initState() {
    super.initState();
    // Figure 4.3's optional fragment: the budget is fetched only when this
    // screen is opened.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) context.read<ForecastController>().loadBudget();
    });
  }

  @override
  Widget build(BuildContext context) {
    final controller = context.watch<ForecastController>();
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        ContextLine(
          '${controller.householdId}  |  ${monthLabel(controller.month!)}',
        ),
        const SyntheticNotice(),
        const SizedBox(height: 16),
        ForecastStatus(builder: (_) => const [BudgetComparison()]),
      ],
    );
  }
}

/// The budget request's own states, then the paired bars.
class BudgetComparison extends StatelessWidget {
  const BudgetComparison({super.key});

  @override
  Widget build(BuildContext context) {
    final controller = context.watch<ForecastController>();
    final budget = controller.budget;

    return switch (budget.state) {
      LoadState.idle ||
      LoadState.loading => LoadingView(waking: budget.waking, what: 'budget'),
      LoadState.error => ErrorView(
        error: budget.error!,
        onRetry: () => controller.loadBudget(force: true),
      ),
      LoadState.loaded => _Comparison(controller: controller),
    };
  }
}

class _Comparison extends StatelessWidget {
  const _Comparison({required this.controller});
  final ForecastController controller;

  @override
  Widget build(BuildContext context) {
    final forecast = controller.forecast.value!;
    final allocated = controller.budget.value!.allocated;
    final scheme = Theme.of(context).colorScheme;
    final budgetColor = scheme.outline;
    final forecastColor = scheme.onSurface;

    // An unknown household, or one that declared no budget, is a 200 with an
    // empty mapping: nothing to compare against, not an error.
    if (allocated.isEmpty) {
      return Container(
        key: const Key('no-budget'),
        width: double.infinity,
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: scheme.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(8),
        ),
        child: Text(
          'No declared budget for ${controller.householdId}, so there is '
          'nothing to compare the forecast against.',
        ),
      );
    }

    final over = controller.categoriesOverBudget().toSet();
    final rows = forecast.breakdownLargestFirst;
    final budgetOnly =
        allocated.keys
            .where((category) => !forecast.breakdown.containsKey(category))
            .toList()
          ..sort();
    final largest = [
      ...forecast.breakdown.values,
      ...allocated.values,
    ].fold(Decimal.zero, (a, b) => a > b ? a : b);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Container(
          key: const Key('over-summary'),
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: scheme.surfaceContainerHighest,
            border: Border.all(color: scheme.outline),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Text(
            over.isEmpty
                ? 'Forecast is within budget in every category'
                : 'Forecast exceeds budget in ${over.length} '
                      '${over.length == 1 ? 'category' : 'categories'}',
          ),
        ),
        const SizedBox(height: 14),
        Wrap(
          spacing: 24,
          children: [
            _Legend(color: budgetColor, label: 'budget'),
            _Legend(color: forecastColor, label: 'forecast'),
          ],
        ),
        const SizedBox(height: 12),
        for (final row in rows)
          _PairRow(
            category: row.key,
            budget: allocated[row.key],
            forecast: row.value,
            largest: largest,
            over: over.contains(row.key),
            budgetColor: budgetColor,
            forecastColor: forecastColor,
          ),
        for (final category in budgetOnly)
          _PairRow(
            category: category,
            budget: allocated[category],
            forecast: Decimal.zero,
            largest: largest,
            over: false,
            budgetColor: budgetColor,
            forecastColor: forecastColor,
          ),
      ],
    );
  }
}

class _PairRow extends StatelessWidget {
  const _PairRow({
    required this.category,
    required this.budget,
    required this.forecast,
    required this.largest,
    required this.over,
    required this.budgetColor,
    required this.forecastColor,
  });

  final String category;
  final Decimal? budget;
  final Decimal forecast;
  final Decimal largest;
  final bool over;
  final Color budgetColor;
  final Color forecastColor;

  @override
  Widget build(BuildContext context) {
    final budget = this.budget;
    return Padding(
      key: Key('budget-row-$category'),
      padding: const EdgeInsets.only(bottom: 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(child: Text(category)),
              if (over)
                Container(
                  key: Key('over-$category'),
                  padding: const EdgeInsets.symmetric(
                    horizontal: 10,
                    vertical: 2,
                  ),
                  decoration: BoxDecoration(
                    border: Border.all(width: 1.5),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: const Text(
                    'over',
                    style: TextStyle(fontWeight: FontWeight.bold),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 4),
          FractionBar(
            fraction: budget == null ? 0 : fractionOf(budget, largest),
            color: budgetColor,
            height: 10,
          ),
          const SizedBox(height: 3),
          FractionBar(
            fraction: fractionOf(forecast, largest),
            color: forecastColor,
            height: 10,
          ),
          const SizedBox(height: 3),
          Text(
            'Budget ${budget == null ? 'not declared' : kes(budget)}'
            '  ·  Forecast ${kes(forecast)}',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ),
    );
  }
}

class _Legend extends StatelessWidget {
  const _Legend({required this.color, required this.label});
  final Color color;
  final String label;

  @override
  Widget build(BuildContext context) => Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      Container(width: 22, height: 12, color: color),
      const SizedBox(width: 6),
      Text(label),
    ],
  );
}

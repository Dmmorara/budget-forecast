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
import '../theme.dart';
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
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
      children: [
        ContextLine(
          '${controller.householdId}  |  ${monthLabel(controller.month!)}',
        ),
        const SyntheticNotice(),
        const SizedBox(height: 16),
        ForecastStatus(
          builder: (_) => const [SectionCard(child: BudgetComparison())],
        ),
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
    // Two series of one hue: budget the lighter step, forecast the darker.
    const budgetColor = Palette.sage;
    const forecastColor = Palette.forest;

    // An unknown household, or one that declared no budget, is a 200 with an
    // empty mapping: nothing to compare against, not an error.
    if (allocated.isEmpty) {
      return NoticeBanner(
        key: const Key('no-budget'),
        icon: Icons.info_outline_rounded,
        background: Palette.mint,
        foreground: Palette.forest,
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
        NoticeBanner(
          key: const Key('over-summary'),
          icon: over.isEmpty ? Icons.eco_outlined : Icons.warning_amber_rounded,
          background: over.isEmpty ? Palette.mint : Palette.overBg,
          foreground: over.isEmpty ? Palette.forest : Palette.over,
          child: Text(
            over.isEmpty
                ? 'Forecast is within budget in every category'
                : 'Forecast exceeds budget in ${over.length} '
                      '${over.length == 1 ? 'category' : 'categories'}',
            style: Theme.of(context).textTheme.titleSmall
                ?.copyWith(color: over.isEmpty ? Palette.forest : Palette.over),
          ),
        ),
        const SizedBox(height: 18),
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
      padding: const EdgeInsets.only(bottom: 18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              IconTile(categoryIcon(category), size: 32),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  category,
                  style: Theme.of(context).textTheme.titleSmall,
                ),
              ),
              if (over)
                Container(
                  key: Key('over-$category'),
                  padding: const EdgeInsets.symmetric(
                    horizontal: 10,
                    vertical: 3,
                  ),
                  decoration: BoxDecoration(
                    color: Palette.overBg,
                    borderRadius: BorderRadius.circular(100),
                  ),
                  child: Text(
                    'over',
                    style: Theme.of(context).textTheme.labelMedium?.copyWith(
                      color: Palette.over,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 8),
          FractionBar(
            fraction: budget == null ? 0 : fractionOf(budget, largest),
            color: budgetColor,
            height: 8,
          ),
          // The 2 px surface gap between the paired bars.
          const SizedBox(height: 2),
          FractionBar(
            fraction: fractionOf(forecast, largest),
            color: forecastColor,
            height: 8,
          ),
          const SizedBox(height: 6),
          Text(
            'Budget ${budget == null ? 'not declared' : kes(budget)}'
            '  ·  Forecast ${kes(forecast)}',
            style: Theme.of(context).textTheme.bodySmall
                ?.copyWith(color: Palette.muted),
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
      Container(
        width: 14,
        height: 14,
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(4),
        ),
      ),
      const SizedBox(width: 6),
      Text(label),
    ],
  );
}

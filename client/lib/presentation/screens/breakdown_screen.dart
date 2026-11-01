/// Category breakdown — wireframe 4.13c, FR-12.
library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../data/models.dart';
import '../../state/forecast_controller.dart';
import '../format.dart';
import '../widgets/common.dart';
import 'dashboard_screen.dart';

class BreakdownScreen extends StatelessWidget {
  const BreakdownScreen({super.key});

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
        ForecastStatus(builder: (result) => [BreakdownList(result: result)]),
      ],
    );
  }
}

/// Every category largest first, bars scaled to the largest, and a total
/// that is the sum of the rows — the same figure as the dashboard.
class BreakdownList extends StatelessWidget {
  const BreakdownList({super.key, required this.result});
  final ForecastResult result;

  @override
  Widget build(BuildContext context) {
    final rows = result.breakdownLargestFirst;
    if (rows.isEmpty) return const Text('No categories in this forecast.');
    final largest = rows.first.value;
    final total = sum(rows.map((row) => row.value));
    final barColor = Theme.of(context).colorScheme.outline;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          'Sorted largest first',
          style: Theme.of(context).textTheme.labelLarge,
        ),
        const SizedBox(height: 8),
        for (final row in rows)
          Padding(
            key: Key('category-${row.key}'),
            padding: const EdgeInsets.only(bottom: 10),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(
                  children: [
                    Expanded(child: Text(row.key)),
                    Text(kes(row.value)),
                  ],
                ),
                const SizedBox(height: 4),
                FractionBar(
                  fraction: fractionOf(row.value, largest),
                  color: barColor,
                ),
              ],
            ),
          ),
        const Divider(),
        Row(
          children: [
            const Expanded(
              child: Text(
                'Total = sum of categories',
                style: TextStyle(fontStyle: FontStyle.italic),
              ),
            ),
            Text(
              kes(total),
              key: const Key('breakdown-total'),
              style: const TextStyle(fontWeight: FontWeight.bold),
            ),
          ],
        ),
      ],
    );
  }
}

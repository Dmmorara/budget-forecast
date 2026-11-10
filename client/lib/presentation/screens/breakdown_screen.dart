/// Category breakdown — wireframe 4.13c, FR-12.
library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../data/models.dart';
import '../../state/forecast_controller.dart';
import '../format.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'dashboard_screen.dart';

class BreakdownScreen extends StatelessWidget {
  const BreakdownScreen({super.key});

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
          builder: (result) => [
            SectionCard(child: BreakdownList(result: result)),
          ],
        ),
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
    final textTheme = Theme.of(context).textTheme;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          'Sorted largest first',
          style: textTheme.labelLarge?.copyWith(color: Palette.muted),
        ),
        const SizedBox(height: 8),
        for (final (i, row) in rows.indexed)
          Padding(
            key: Key('category-${row.key}'),
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Row(
              children: [
                IconTile(categoryIcon(row.key), size: 40, dark: i == 0),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text(row.key, style: textTheme.titleSmall),
                          ),
                          Text(kes(row.value), style: textTheme.titleSmall),
                        ],
                      ),
                      const SizedBox(height: 6),
                      Row(
                        children: [
                          // One series, so one hue and no legend: the
                          // heading says what the bars are.
                          Expanded(
                            child: FractionBar(
                              fraction: fractionOf(row.value, largest),
                              color: Palette.forest,
                              height: 8,
                            ),
                          ),
                          const SizedBox(width: 10),
                          SizedBox(
                            width: 40,
                            child: Text(
                              percentOf(row.value, total),
                              textAlign: TextAlign.right,
                              style: textTheme.bodySmall?.copyWith(
                                color: Palette.muted,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        const SizedBox(height: 8),
        const Divider(),
        const SizedBox(height: 12),
        Row(
          children: [
            const Expanded(
              child: Text(
                'Total = sum of categories',
                style: TextStyle(
                  fontStyle: FontStyle.italic,
                  color: Palette.muted,
                ),
              ),
            ),
            Text(
              kes(total),
              key: const Key('breakdown-total'),
              style: textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.w700,
              ),
            ),
          ],
        ),
      ],
    );
  }
}

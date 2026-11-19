/// Simulate: a demo household's history, built up live (data/demo.dart).
///
/// Shows the month in progress and how far the household is from a forecast,
/// and offers the three things a presenter does: simulate a month from the
/// budget, add a single spend to the month in progress, and edit the budget.
/// Every action reloads the forecast screens.
library;

import 'package:decimal/decimal.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../data/demo.dart';
import '../../state/demo_controller.dart';
import '../format.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'demo_budget_screen.dart';

class DemoScreen extends StatelessWidget {
  const DemoScreen({super.key, required this.onOpenForecast});

  final VoidCallback onOpenForecast;

  @override
  Widget build(BuildContext context) {
    final demo = context.watch<DemoController>();
    final household = demo.household!;

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
      children: [
        ContextLine('${household.name}  |  ${household.userId}'),
        const SyntheticNotice(),
        const SizedBox(height: 16),
        _Progress(household: household, onOpenForecast: onOpenForecast),
        const SizedBox(height: 16),
        SectionCard(
          title: 'Simulate spending',
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'Fills in ${monthLabel(household.month)} from the budget, '
                'with the ups and downs of a real month, and moves on to the '
                'next. Anything added below is kept.',
                style: const TextStyle(color: Palette.muted),
              ),
              const SizedBox(height: 14),
              Wrap(
                spacing: 10,
                runSpacing: 10,
                children: [
                  FilledButton.icon(
                    key: const Key('demo-simulate-1'),
                    onPressed: demo.busy ? null : () => demo.simulate(1),
                    icon: const Icon(Icons.skip_next_rounded),
                    label: const Text('Simulate 1 month'),
                  ),
                  OutlinedButton(
                    key: const Key('demo-simulate-3'),
                    onPressed: demo.busy ? null : () => demo.simulate(3),
                    child: const Text('Simulate 3 months'),
                  ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),
        _AddSpend(household: household),
        if (demo.error case final error?) ...[
          const SizedBox(height: 12),
          Text(
            error.message,
            key: const Key('demo-error'),
            style: const TextStyle(color: Palette.over),
          ),
        ],
        const SizedBox(height: 16),
        Wrap(
          spacing: 10,
          runSpacing: 10,
          children: [
            OutlinedButton.icon(
              key: const Key('demo-edit-budget'),
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const DemoBudgetScreen()),
              ),
              icon: const Icon(Icons.account_balance_wallet_outlined),
              label: const Text('Edit budget'),
            ),
            TextButton(
              key: const Key('demo-sign-out'),
              onPressed: demo.signOut,
              child: const Text('Log out'),
            ),
          ],
        ),
      ],
    );
  }
}

/// Where the household is: the month in progress, and months of history
/// against the three a forecast needs.
class _Progress extends StatelessWidget {
  const _Progress({required this.household, required this.onOpenForecast});

  final DemoHousehold household;
  final VoidCallback onOpenForecast;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final months = household.historyMonths;
    final ready = months >= monthsForForecast;
    final toGo = monthsForForecast - months;

    return Card(
      color: Palette.forest,
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Month in progress',
              style: textTheme.labelLarge?.copyWith(
                color: Palette.onForestMuted,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              monthLabel(household.month),
              key: const Key('demo-month'),
              style: textTheme.headlineSmall?.copyWith(
                color: Colors.white,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                for (var i = 0; i < monthsForForecast; i++)
                  Expanded(
                    child: Container(
                      height: 8,
                      margin: EdgeInsets.only(
                        right: i < monthsForForecast - 1 ? 6 : 0,
                      ),
                      decoration: BoxDecoration(
                        color: i < months
                            ? Palette.sageOnDark
                            : Colors.white.withValues(alpha: 0.15),
                        borderRadius: BorderRadius.circular(100),
                      ),
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 10),
            Text(
              ready
                  ? '$months months of history. The forecast for '
                        '${monthLabel(household.month)} is ready.'
                  : '$months of $monthsForForecast months of history. '
                        '$toGo more ${toGo == 1 ? 'month' : 'months'} before '
                        'a forecast can be made.',
              key: const Key('demo-progress'),
              style: textTheme.bodyMedium?.copyWith(color: Colors.white),
            ),
            if (ready) ...[
              const SizedBox(height: 14),
              FilledButton(
                key: const Key('demo-open-forecast'),
                onPressed: onOpenForecast,
                style: FilledButton.styleFrom(
                  backgroundColor: Colors.white,
                  foregroundColor: Palette.forest,
                ),
                child: const Text('See the forecast'),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// One transaction in the month in progress, e.g. a one-off purchase, to show
/// what it does to next month's forecast.
class _AddSpend extends StatefulWidget {
  const _AddSpend({required this.household});
  final DemoHousehold household;

  @override
  State<_AddSpend> createState() => _AddSpendState();
}

class _AddSpendState extends State<_AddSpend> {
  final _amount = TextEditingController();
  String? _category;

  @override
  void initState() {
    super.initState();
    context.read<DemoController>().loadCategories();
  }

  @override
  void dispose() {
    _amount.dispose();
    super.dispose();
  }

  Future<void> _add() async {
    final amount = Decimal.tryParse(_amount.text);
    final category = _category;
    if (amount == null || amount <= Decimal.zero || category == null) return;
    final ok = await context.read<DemoController>().addSpend(category, amount);
    if (ok && mounted) _amount.clear();
  }

  @override
  Widget build(BuildContext context) {
    final demo = context.watch<DemoController>();
    final household = widget.household;
    final categories = {
      ...household.budget.keys,
      ...?demo.categories?.categories,
    }.toList()..sort();
    final spent = household.spentThisMonth.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));

    return SectionCard(
      title: 'Add a spend to ${monthLabel(household.month)}',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          DropdownButtonFormField<String>(
            key: const Key('demo-spend-category'),
            initialValue: _category,
            isExpanded: true,
            hint: const Text('Category'),
            items: [
              for (final c in categories)
                DropdownMenuItem(value: c, child: Text(c)),
            ],
            onChanged: (c) => setState(() => _category = c),
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                child: TextField(
                  key: const Key('demo-spend-amount'),
                  controller: _amount,
                  keyboardType: TextInputType.number,
                  inputFormatters: [
                    FilteringTextInputFormatter.digitsOnly,
                    LengthLimitingTextInputFormatter(8),
                  ],
                  decoration: const InputDecoration(
                    prefixText: 'KSh ',
                    hintText: 'Amount',
                  ),
                  onSubmitted: (_) => _add(),
                ),
              ),
              const SizedBox(width: 10),
              FilledButton(
                key: const Key('demo-spend-add'),
                onPressed: demo.busy ? null : _add,
                child: const Text('Add'),
              ),
            ],
          ),
          if (spent.isNotEmpty) ...[
            const SizedBox(height: 14),
            Text(
              'Added so far this month',
              style: Theme.of(context).textTheme.labelLarge,
            ),
            for (final e in spent)
              Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Row(
                  children: [
                    Expanded(child: Text(e.key)),
                    Text(kes(e.value)),
                  ],
                ),
              ),
          ],
        ],
      ),
    );
  }
}

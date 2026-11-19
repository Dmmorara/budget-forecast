/// A demo household's monthly budget, per category.
///
/// When [onboarding], the form is prefilled with a typical sandbox budget so a
/// presenter can accept it in one tap, and saving opens the forecast screens.
/// Otherwise it edits the current budget and returns.
library;

import 'package:decimal/decimal.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../state/demo_controller.dart';
import '../format.dart';
import '../theme.dart';
import '../widgets/common.dart';

class DemoBudgetScreen extends StatefulWidget {
  const DemoBudgetScreen({super.key, this.onboarding = false});

  final bool onboarding;

  @override
  State<DemoBudgetScreen> createState() => _DemoBudgetScreenState();
}

class _DemoBudgetScreenState extends State<DemoBudgetScreen> {
  final _fields = <String, TextEditingController>{};

  /// Shown without unfolding "More categories". Decided when a field is
  /// made, so a field does not jump between the two while it is typed in.
  final _main = <String>{};

  @override
  void initState() {
    super.initState();
    final demo = context.read<DemoController>();
    demo.loadCategories().then((_) {
      if (mounted) setState(_fill);
    });
    _fill();
  }

  /// One field per category, keeping anything already typed.
  void _fill() {
    final demo = context.read<DemoController>();
    final categories = demo.categories;
    final budget = demo.household?.budget ?? const {};
    final names = {...?categories?.categories, ...budget.keys};
    for (final c in names) {
      if (_fields.containsKey(c)) continue;
      final start =
          budget[c] ??
          (widget.onboarding && budget.isEmpty ? categories?.typical[c] : null);
      if (start != null && start > Decimal.zero ||
          (categories?.typical.containsKey(c) ?? false)) {
        _main.add(c);
      }
      _fields[c] = TextEditingController(
        text: start == null || start == Decimal.zero
            ? ''
            : start.round().toString(),
      )..addListener(() => setState(() {}));
    }
  }

  @override
  void dispose() {
    for (final f in _fields.values) {
      f.dispose();
    }
    super.dispose();
  }

  Map<String, Decimal> get _allocated => {
    for (final e in _fields.entries)
      e.key: Decimal.tryParse(e.value.text) ?? Decimal.zero,
  };

  Future<void> _save() async {
    final demo = context.read<DemoController>();
    if (!await demo.saveBudget(_allocated) || !mounted) return;
    Navigator.of(context).pop();
    if (widget.onboarding) await demo.enter();
  }

  @override
  Widget build(BuildContext context) {
    final demo = context.watch<DemoController>();
    final names = _fields.keys.toList()..sort();
    final main = [
      for (final c in names)
        if (_main.contains(c)) c,
    ];
    final others = [
      for (final c in names)
        if (!_main.contains(c)) c,
    ];
    final total = sum(_allocated.values);

    return Scaffold(
      appBar: AppBar(
        title: Text(widget.onboarding ? 'Your monthly budget' : 'Edit budget'),
      ),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 640),
            child: ListView(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
              children: [
                ContextLine(demo.household?.name ?? ''),
                const SyntheticNotice(),
                const SizedBox(height: 12),
                if (widget.onboarding)
                  Text(
                    'Filled in with a typical household budget. Change any '
                    'amount, or leave a category empty to spend nothing on it. '
                    'Simulated months are drawn from these figures.',
                    style: Theme.of(context).textTheme.bodyMedium
                        ?.copyWith(color: Palette.muted),
                  ),
                const SizedBox(height: 16),
                if (_fields.isEmpty)
                  const LoadingView(waking: false, what: 'categories')
                else
                  SectionCard(
                    child: Column(
                      children: [
                        for (final c in main) _AmountRow(c, _fields[c]!),
                        if (others.isNotEmpty)
                          ExpansionTile(
                            tilePadding: EdgeInsets.zero,
                            title: Text('More categories (${others.length})'),
                            children: [
                              for (final c in others)
                                _AmountRow(c, _fields[c]!),
                            ],
                          ),
                      ],
                    ),
                  ),
                const SizedBox(height: 16),
                SectionCard(
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(
                          'Total per month',
                          style: Theme.of(context).textTheme.titleMedium,
                        ),
                      ),
                      Text(
                        kes(total),
                        key: const Key('demo-budget-total'),
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                    ],
                  ),
                ),
                if (demo.error case final error?) ...[
                  const SizedBox(height: 12),
                  Text(
                    error.message,
                    style: const TextStyle(color: Palette.over),
                  ),
                ],
                const SizedBox(height: 20),
                FilledButton(
                  key: const Key('demo-budget-save'),
                  onPressed: demo.busy || total <= Decimal.zero ? null : _save,
                  style: FilledButton.styleFrom(
                    minimumSize: const Size.fromHeight(56),
                  ),
                  child: Text(
                    widget.onboarding ? 'Save and continue' : 'Save budget',
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _AmountRow extends StatelessWidget {
  const _AmountRow(this.category, this.field);

  final String category;
  final TextEditingController field;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 6),
    child: Row(
      children: [
        Expanded(child: Text(category)),
        const SizedBox(width: 12),
        SizedBox(
          width: 150,
          child: TextField(
            key: Key('demo-budget-$category'),
            controller: field,
            textAlign: TextAlign.end,
            keyboardType: TextInputType.number,
            inputFormatters: [
              FilteringTextInputFormatter.digitsOnly,
              LengthLimitingTextInputFormatter(8),
            ],
            decoration: const InputDecoration(
              prefixText: 'KSh ',
              hintText: '0',
              isDense: true,
            ),
          ),
        ),
      ],
    ),
  );
}

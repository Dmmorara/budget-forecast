/// Household selection — wireframe 4.12a, FR-10.
library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../data/models.dart';
import '../../state/forecast_controller.dart';
import '../format.dart';
import '../widgets/common.dart';

class HouseholdScreen extends StatefulWidget {
  const HouseholdScreen({super.key});

  @override
  State<HouseholdScreen> createState() => _HouseholdScreenState();
}

class _HouseholdScreenState extends State<HouseholdScreen> {
  final _formKey = GlobalKey<FormState>();
  final _idField = TextEditingController();
  late int _month;
  late int _year;
  late List<int> _years;

  @override
  void initState() {
    super.initState();
    // Default to the month straight after the data ends — the month a
    // forecast is genuinely for. Without DATA_LAST_MONTH, the current month.
    final controller = context.read<ForecastController>();
    final now = DateTime.now();
    final start =
        controller.dataLastMonth?.plus(1) ??
        controller.month ??
        YearMonth(now.year, now.month);
    _month = start.month;
    _year = start.year;
    _years = [for (var y = start.year - 2; y <= start.year + 2; y++) y];
  }

  @override
  void dispose() {
    _idField.dispose();
    super.dispose();
  }

  void _show(String id) {
    context.read<ForecastController>().selectHousehold(
      id,
      YearMonth(_year, _month),
    );
  }

  void _submit() {
    if (_formKey.currentState!.validate()) _show(_idField.text);
  }

  @override
  Widget build(BuildContext context) {
    final recent = context.watch<ForecastController>().recentHouseholds;
    final textTheme = Theme.of(context).textTheme;

    return Scaffold(
      appBar: AppBar(title: const Text('Budget forecast')),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 520),
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                const SyntheticNotice(),
                const SizedBox(height: 24),
                Form(
                  key: _formKey,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      TextFormField(
                        key: const Key('household-id'),
                        controller: _idField,
                        decoration: const InputDecoration(
                          labelText: 'Household ID',
                          hintText: 'e.g. h015',
                          border: OutlineInputBorder(),
                        ),
                        autocorrect: false,
                        textInputAction: TextInputAction.go,
                        onFieldSubmitted: (_) => _submit(),
                        validator: (value) => (value ?? '').trim().isEmpty
                            ? 'Enter a household ID'
                            : null,
                      ),
                      const SizedBox(height: 16),
                      Row(
                        children: [
                          Expanded(
                            child: DropdownButtonFormField<int>(
                              key: const Key('month'),
                              initialValue: _month,
                              isExpanded: true,
                              decoration: const InputDecoration(
                                labelText: 'Month',
                                border: OutlineInputBorder(),
                              ),
                              items: [
                                for (var m = 1; m <= 12; m++)
                                  DropdownMenuItem(
                                    value: m,
                                    child: Text(monthName(m)),
                                  ),
                              ],
                              onChanged: (m) => setState(() => _month = m!),
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: DropdownButtonFormField<int>(
                              key: const Key('year'),
                              initialValue: _year,
                              isExpanded: true,
                              decoration: const InputDecoration(
                                labelText: 'Year',
                                border: OutlineInputBorder(),
                              ),
                              items: [
                                for (final y in _years)
                                  DropdownMenuItem(value: y, child: Text('$y')),
                              ],
                              onChanged: (y) => setState(() => _year = y!),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 20),
                      FilledButton(
                        key: const Key('show-forecast'),
                        onPressed: _submit,
                        style: FilledButton.styleFrom(
                          minimumSize: const Size.fromHeight(52),
                        ),
                        child: const Text('Show forecast'),
                      ),
                    ],
                  ),
                ),
                if (recent.isNotEmpty) ...[
                  const SizedBox(height: 28),
                  Text('Recent households', style: textTheme.titleSmall),
                  const SizedBox(height: 4),
                  for (final id in recent)
                    ListTile(
                      key: Key('recent-$id'),
                      title: Text(id),
                      trailing: const Icon(Icons.chevron_right),
                      contentPadding: EdgeInsets.zero,
                      shape: Border(
                        bottom: BorderSide(
                          color: Theme.of(context).dividerColor,
                        ),
                      ),
                      onTap: () => _show(id),
                    ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Household selection — wireframe 4.12a, FR-10.
library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../data/models.dart';
import '../../state/forecast_controller.dart';
import '../format.dart';
import '../theme.dart';
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
      backgroundColor: Palette.forest,
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 520),
            child: ListView(
              padding: const EdgeInsets.fromLTRB(24, 20, 24, 32),
              children: [
                Row(
                  children: [
                    Container(
                      width: 36,
                      height: 36,
                      decoration: BoxDecoration(
                        color: Colors.white.withValues(alpha: 0.12),
                        shape: BoxShape.circle,
                      ),
                      child: const Icon(
                        Icons.insights_rounded,
                        color: Colors.white,
                        size: 20,
                      ),
                    ),
                    const SizedBox(width: 10),
                    Flexible(
                      child: Text(
                        'Budget forecast',
                        style: textTheme.titleMedium?.copyWith(
                          color: Colors.white,
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 36),
                Text.rich(
                  TextSpan(
                    children: const [
                      TextSpan(text: 'Next month,\n'),
                      TextSpan(
                        text: 'seen early.',
                        style: TextStyle(color: Palette.sageOnDark),
                      ),
                    ],
                    style: textTheme.displaySmall?.copyWith(
                      color: Colors.white,
                      fontWeight: FontWeight.w700,
                      height: 1.1,
                    ),
                  ),
                ),
                const SizedBox(height: 14),
                Text(
                  'Enter a household to see its likely spending range, '
                  'where the money goes, and how it compares with the budget.',
                  style: textTheme.bodyLarge?.copyWith(
                    color: Palette.onForestMuted,
                  ),
                ),
                const SizedBox(height: 18),
                const SyntheticNotice(onDark: true),
                const SizedBox(height: 32),
                // The theme's forest focus ring would vanish against the
                // forest background; a light one shows which field is active.
                Theme(
                  data: Theme.of(context).copyWith(
                    inputDecorationTheme: Theme.of(context).inputDecorationTheme
                        .copyWith(
                          focusedBorder: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(Radii.field),
                            borderSide: const BorderSide(
                              color: Palette.sageOnDark,
                              width: 3,
                            ),
                          ),
                        ),
                  ),
                  child: Form(
                    key: _formKey,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const _FieldLabel('Household ID'),
                        TextFormField(
                          key: const Key('household-id'),
                          controller: _idField,
                          decoration: const InputDecoration(
                            hintText: 'e.g. h015',
                            prefixIcon: Icon(Icons.home_outlined),
                            errorStyle: TextStyle(color: _errorOnForest),
                          ),
                          autocorrect: false,
                          textInputAction: TextInputAction.go,
                          onFieldSubmitted: (_) => _submit(),
                          validator: (value) => (value ?? '').trim().isEmpty
                              ? 'Enter a household ID'
                              : null,
                        ),
                        const SizedBox(height: 18),
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.stretch,
                                children: [
                                  const _FieldLabel('Month'),
                                  DropdownButtonFormField<int>(
                                    key: const Key('month'),
                                    initialValue: _month,
                                    isExpanded: true,
                                    dropdownColor: Palette.surface,
                                    borderRadius: BorderRadius.circular(
                                      Radii.field,
                                    ),
                                    items: [
                                      for (var m = 1; m <= 12; m++)
                                        DropdownMenuItem(
                                          value: m,
                                          child: Text(monthName(m)),
                                        ),
                                    ],
                                    onChanged: (m) =>
                                        setState(() => _month = m!),
                                  ),
                                ],
                              ),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.stretch,
                                children: [
                                  const _FieldLabel('Year'),
                                  DropdownButtonFormField<int>(
                                    key: const Key('year'),
                                    initialValue: _year,
                                    isExpanded: true,
                                    dropdownColor: Palette.surface,
                                    borderRadius: BorderRadius.circular(
                                      Radii.field,
                                    ),
                                    items: [
                                      for (final y in _years)
                                        DropdownMenuItem(
                                          value: y,
                                          child: Text('$y'),
                                        ),
                                    ],
                                    onChanged: (y) =>
                                        setState(() => _year = y!),
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 28),
                        FilledButton(
                          key: const Key('show-forecast'),
                          onPressed: _submit,
                          style: FilledButton.styleFrom(
                            backgroundColor: Colors.white,
                            foregroundColor: Palette.forest,
                            minimumSize: const Size.fromHeight(56),
                          ),
                          child: const Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Text('Show forecast'),
                              SizedBox(width: 8),
                              Icon(Icons.arrow_forward_rounded, size: 20),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                if (recent.isNotEmpty) ...[
                  const SizedBox(height: 32),
                  Text(
                    'Recent households',
                    style: textTheme.titleSmall?.copyWith(color: Colors.white),
                  ),
                  const SizedBox(height: 10),
                  for (final id in recent)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 8),
                      child: ListTile(
                        key: Key('recent-$id'),
                        title: Text(id),
                        leading: const Icon(Icons.history_rounded),
                        trailing: const Icon(Icons.chevron_right_rounded),
                        iconColor: Palette.onForestMuted,
                        textColor: Colors.white,
                        tileColor: Colors.white.withValues(alpha: 0.08),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(Radii.tile),
                        ),
                        onTap: () => _show(id),
                      ),
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

/// Validation messages sit on the forest background, not on the field.
const _errorOnForest = Color(0xFFFFD3C2);

/// A field's label, above it rather than inside, so it stays readable on the
/// forest background whatever the field holds.
class _FieldLabel extends StatelessWidget {
  const _FieldLabel(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(left: 4, bottom: 8),
    child: Text(
      text,
      style: Theme.of(context).textTheme.labelLarge
          ?.copyWith(color: Palette.onForestMuted),
    ),
  );
}

/// The frame around the forecast screens.
///
/// Phone (wireframes 4.12b-4.14e): an app bar whose back arrow changes
/// household, and Forecast / Budget / Months in a bottom navigation bar.
/// Desktop (4.14f): the same three destinations in a side panel, with the
/// household at its foot, and breakdown and budget side by side on Forecast.
library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/forecast_controller.dart';
import 'screens/breakdown_screen.dart';
import 'screens/budget_screen.dart';
import 'screens/comparison_screen.dart';
import 'screens/dashboard_screen.dart';

/// At or above this width the side navigation layout is used (NFR-10).
const wideBreakpoint = 900.0;

enum _Tab { forecast, budget, months }

class HomeShell extends StatefulWidget {
  const HomeShell({super.key});

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  _Tab _tab = _Tab.forecast;

  /// On a phone the breakdown is a step inside the Forecast tab (4.13c keeps
  /// Forecast selected), so back returns to the dashboard, not the household.
  bool _showBreakdown = false;

  void _select(_Tab tab) => setState(() {
    _tab = tab;
    _showBreakdown = false;
  });

  /// Back: leave the breakdown first, otherwise change household (Figure
  /// 4.8, Loaded -> Idle).
  void _back() {
    if (_showBreakdown) {
      setState(() => _showBreakdown = false);
    } else {
      context.read<ForecastController>().changeHousehold();
    }
  }

  String _title(String householdId) => switch (_tab) {
    _Tab.forecast when _showBreakdown => 'Category breakdown',
    _Tab.forecast => householdId,
    _Tab.budget => 'Budget vs forecast',
    _Tab.months => 'Compare months',
  };

  @override
  Widget build(BuildContext context) {
    final householdId = context.select<ForecastController, String>(
      (c) => c.householdId ?? '',
    );

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _back();
      },
      child: LayoutBuilder(
        builder: (context, constraints) {
          final wide = constraints.maxWidth >= wideBreakpoint;
          final body = _body(wide);
          return wide
              ? _wideScaffold(householdId, body)
              : _narrowScaffold(householdId, body);
        },
      ),
    );
  }

  Widget _body(bool wide) => switch (_tab) {
    _Tab.forecast when _showBreakdown && !wide => const BreakdownScreen(),
    _Tab.forecast => DashboardScreen(
      wide: wide,
      onOpenBreakdown: () => setState(() => _showBreakdown = true),
      onOpenBudget: () => _select(_Tab.budget),
      onOpenMonths: () => _select(_Tab.months),
    ),
    _Tab.budget => const BudgetScreen(),
    _Tab.months => const ComparisonScreen(),
  };

  Widget _narrowScaffold(String householdId, Widget body) => Scaffold(
    appBar: AppBar(
      leading: IconButton(
        key: const Key('back'),
        tooltip: _showBreakdown ? 'Back to forecast' : 'Change household',
        icon: const Icon(Icons.arrow_back),
        onPressed: _back,
      ),
      title: Text(_title(householdId)),
    ),
    body: SafeArea(child: body),
    bottomNavigationBar: NavigationBar(
      selectedIndex: _tab.index,
      onDestinationSelected: (i) => _select(_Tab.values[i]),
      destinations: const [
        NavigationDestination(
          icon: Icon(Icons.insights_outlined),
          label: 'Forecast',
        ),
        NavigationDestination(
          icon: Icon(Icons.account_balance_wallet_outlined),
          label: 'Budget',
        ),
        NavigationDestination(
          icon: Icon(Icons.calendar_view_month_outlined),
          label: 'Months',
        ),
      ],
    ),
  );

  Widget _wideScaffold(String householdId, Widget body) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('budget-forecast')),
      body: Row(
        children: [
          // A Material, not a coloured Container, so the selected item's
          // highlight and ink are painted on top of the panel's colour.
          Material(
            color: scheme.surfaceContainerLow,
            child: SizedBox(
              width: 220,
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    for (final tab in _Tab.values)
                      ListTile(
                        key: Key('side-${tab.name}'),
                        selected: _tab == tab,
                        title: Text(
                          switch (tab) {
                            _Tab.forecast => 'Forecast',
                            _Tab.budget => 'Budget',
                            _Tab.months => 'Months',
                          },
                          style: TextStyle(
                            fontWeight: _tab == tab
                                ? FontWeight.bold
                                : FontWeight.normal,
                          ),
                        ),
                        onTap: () => _select(tab),
                      ),
                    const Spacer(),
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 16),
                      child: Text(
                        'Household\n$householdId',
                        style: TextStyle(color: scheme.onSurfaceVariant),
                      ),
                    ),
                    const SizedBox(height: 8),
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 8),
                      child: TextButton(
                        key: const Key('change-household'),
                        onPressed: _back,
                        child: const Text('Change household'),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
          Expanded(
            child: Align(
              alignment: Alignment.topCenter,
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 1100),
                child: body,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

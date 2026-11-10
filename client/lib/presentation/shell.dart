/// The frame around the forecast screens.
///
/// Phone (wireframes 4.12b-4.14e): an app bar whose round back button changes
/// household, and Forecast / Budget / Months in a bottom navigation bar.
/// Desktop (4.14f): the same three destinations in a side panel card, with
/// the household at its foot, and breakdown and budget side by side on
/// Forecast.
library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/forecast_controller.dart';
import 'screens/breakdown_screen.dart';
import 'screens/budget_screen.dart';
import 'screens/comparison_screen.dart';
import 'screens/dashboard_screen.dart';
import 'theme.dart';
import 'widgets/common.dart';

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
      toolbarHeight: 68,
      leadingWidth: 72,
      leading: Center(
        child: _CircleButton(
          key: const Key('back'),
          tooltip: _showBreakdown ? 'Back to forecast' : 'Change household',
          icon: Icons.arrow_back_rounded,
          onPressed: _back,
        ),
      ),
      title: Text(_title(householdId), overflow: TextOverflow.ellipsis),
      // Balances the leading button so the title stays centred.
      actions: const [SizedBox(width: 72)],
    ),
    body: SafeArea(child: body),
    bottomNavigationBar: NavigationBar(
      selectedIndex: _tab.index,
      onDestinationSelected: (i) => _select(_Tab.values[i]),
      destinations: const [
        NavigationDestination(
          icon: Icon(Icons.insights_outlined),
          selectedIcon: Icon(Icons.insights_rounded),
          label: 'Forecast',
        ),
        NavigationDestination(
          icon: Icon(Icons.account_balance_wallet_outlined),
          selectedIcon: Icon(Icons.account_balance_wallet_rounded),
          label: 'Budget',
        ),
        NavigationDestination(
          icon: Icon(Icons.bar_chart_outlined),
          selectedIcon: Icon(Icons.bar_chart_rounded),
          label: 'Months',
        ),
      ],
    ),
  );

  Widget _wideScaffold(String householdId, Widget body) {
    final textTheme = Theme.of(context).textTheme;
    return Scaffold(
      body: SafeArea(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.all(16),
              child: Card(
                child: SizedBox(
                  width: 232,
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(14, 22, 14, 14),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Padding(
                          padding: const EdgeInsets.only(left: 8, bottom: 24),
                          child: Row(
                            children: [
                              const IconTile(
                                Icons.insights_rounded,
                                size: 36,
                                dark: true,
                              ),
                              const SizedBox(width: 10),
                              Flexible(
                                child: Text(
                                  'budget-forecast',
                                  style: textTheme.titleMedium,
                                ),
                              ),
                            ],
                          ),
                        ),
                        for (final tab in _Tab.values)
                          Padding(
                            padding: const EdgeInsets.only(bottom: 6),
                            child: _SideItem(
                              key: Key('side-${tab.name}'),
                              selected: _tab == tab,
                              icon: switch (tab) {
                                _Tab.forecast => Icons.insights_rounded,
                                _Tab.budget =>
                                  Icons.account_balance_wallet_rounded,
                                _Tab.months => Icons.bar_chart_rounded,
                              },
                              label: switch (tab) {
                                _Tab.forecast => 'Forecast',
                                _Tab.budget => 'Budget',
                                _Tab.months => 'Months',
                              },
                              onTap: () => _select(tab),
                            ),
                          ),
                        const Spacer(),
                        Container(
                          padding: const EdgeInsets.all(14),
                          decoration: BoxDecoration(
                            color: Palette.cream,
                            borderRadius: BorderRadius.circular(Radii.tile),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              Text(
                                'Household\n$householdId',
                                style: textTheme.bodyMedium?.copyWith(
                                  color: Palette.muted,
                                ),
                              ),
                              const SizedBox(height: 8),
                              TextButton(
                                key: const Key('change-household'),
                                onPressed: _back,
                                child: const Text('Change household'),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
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
      ),
    );
  }
}

/// A round white button, as in the reference header.
class _CircleButton extends StatelessWidget {
  const _CircleButton({
    super.key,
    required this.tooltip,
    required this.icon,
    required this.onPressed,
  });

  final String tooltip;
  final IconData icon;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) => IconButton(
    tooltip: tooltip,
    onPressed: onPressed,
    icon: Icon(icon),
    style: IconButton.styleFrom(
      backgroundColor: Palette.surface,
      foregroundColor: Palette.ink,
      fixedSize: const Size(48, 48),
    ),
  );
}

/// A side-panel destination: a forest pill when selected.
class _SideItem extends StatelessWidget {
  const _SideItem({
    super.key,
    required this.selected,
    required this.icon,
    required this.label,
    required this.onTap,
  });

  final bool selected;
  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final fg = selected ? Colors.white : Palette.muted;
    return Material(
      color: selected ? Palette.forest : Colors.transparent,
      borderRadius: BorderRadius.circular(100),
      child: InkWell(
        borderRadius: BorderRadius.circular(100),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 13),
          child: Row(
            children: [
              Icon(icon, color: fg, size: 20),
              const SizedBox(width: 12),
              Flexible(
                child: Text(
                  label,
                  style: Theme.of(context).textTheme.titleSmall?.copyWith(
                    color: fg,
                    fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

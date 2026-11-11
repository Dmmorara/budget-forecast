/// Forecast dashboard — wireframe 4.12b (phone) and 4.14f (desktop), FR-11.
///
/// Leads with a hero card stating the RANGE and a band placing the point
/// estimate inside it, so the uncertainty is read before the single number.
library;

import 'package:decimal/decimal.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../data/models.dart';
import '../../state/forecast_controller.dart';
import '../format.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'breakdown_screen.dart';
import 'budget_screen.dart';
import 'insights_screen.dart';

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({
    super.key,
    required this.wide,
    required this.onOpenBreakdown,
    required this.onOpenBudget,
    required this.onOpenMonths,
    required this.onOpenInsights,
  });

  /// Desktop layout: breakdown and budget panels side by side beneath the band.
  final bool wide;
  final VoidCallback onOpenBreakdown;
  final VoidCallback onOpenBudget;
  final VoidCallback onOpenMonths;
  final VoidCallback onOpenInsights;

  @override
  Widget build(BuildContext context) {
    final controller = context.watch<ForecastController>();
    final month = controller.month!;

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
      children: [
        MonthStepper(month: month),
        const SizedBox(height: 14),
        const SyntheticNotice(),
        const SizedBox(height: 14),
        ForecastStatus(
          builder: (result) => [
            _RangeSummary(result: result, month: month, wide: wide),
            if (riskNotice(result.riskFlag) case final String notice) ...[
              const SizedBox(height: 12),
              NoticeBanner(
                key: const Key('risk-notice'),
                icon: Icons.warning_amber_rounded,
                background: Palette.cautionBg,
                foreground: Palette.cautionInk,
                child: Text(notice),
              ),
            ],
            const SizedBox(height: 16),
            _WhatChangedPreview(onSeeAll: onOpenInsights),
            const SizedBox(height: 16),
            if (wide)
              _WidePanels(result: result)
            else ...[
              _LargestCategories(result: result, onSeeAll: onOpenBreakdown),
              const SizedBox(height: 16),
              SectionCard(
                title: 'Explore',
                padding: const EdgeInsets.fromLTRB(20, 20, 20, 8),
                child: Column(
                  children: [
                    _LinkRow(
                      icon: Icons.donut_small_outlined,
                      label: 'Category breakdown',
                      detail: 'Every category, largest first',
                      onTap: onOpenBreakdown,
                    ),
                    _LinkRow(
                      icon: Icons.lightbulb_outline_rounded,
                      label: 'Insights',
                      detail: 'What changed, when money goes out, and more',
                      onTap: onOpenInsights,
                    ),
                    _LinkRow(
                      icon: Icons.account_balance_wallet_outlined,
                      label: 'Budget vs forecast',
                      detail: 'The declared budget, category by category',
                      onTap: onOpenBudget,
                    ),
                    _LinkRow(
                      icon: Icons.bar_chart_rounded,
                      label: 'Compare months',
                      detail: 'Forecasts either side of ${monthShort(month)}',
                      onTap: onOpenMonths,
                      last: true,
                    ),
                  ],
                ),
              ),
            ],
          ],
        ),
      ],
    );
  }
}

/// Renders the forecast request's state: loading (and waking), error with
/// retry, insufficient history as an explanation, or [builder]'s content.
/// Shared by every screen that shows the selected month's forecast.
class ForecastStatus extends StatelessWidget {
  const ForecastStatus({super.key, required this.builder});

  final List<Widget> Function(ForecastResult result) builder;

  @override
  Widget build(BuildContext context) {
    final controller = context.watch<ForecastController>();
    final forecast = controller.forecast;

    final Widget content = switch (forecast.state) {
      LoadState.idle ||
      LoadState.loading => LoadingView(waking: forecast.waking),
      LoadState.error => ErrorView(
        error: forecast.error!,
        onRetry: controller.loadForecast,
        onChangeHousehold: controller.changeHousehold,
      ),
      LoadState.loaded
          when forecast.value!.riskFlag == RiskFlag.insufficientHistory =>
        InsufficientHistoryView(
          householdId: controller.householdId!,
          month: controller.month!,
        ),
      LoadState.loaded => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: builder(forecast.value!),
      ),
    };
    return content;
  }
}

class MonthStepper extends StatelessWidget {
  const MonthStepper({super.key, required this.month});
  final YearMonth month;

  @override
  Widget build(BuildContext context) {
    final controller = context.read<ForecastController>();
    Widget arrow(String key, String tooltip, IconData icon, int step) =>
        IconButton(
          key: Key(key),
          tooltip: tooltip,
          icon: Icon(icon),
          onPressed: () => controller.changeMonth(step),
          style: IconButton.styleFrom(
            backgroundColor: Palette.cream,
            foregroundColor: Palette.ink,
          ),
        );

    return Center(
      child: Container(
        padding: const EdgeInsets.all(6),
        decoration: BoxDecoration(
          color: Palette.surface,
          borderRadius: BorderRadius.circular(100),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            arrow(
              'previous-month',
              'Previous month',
              Icons.chevron_left_rounded,
              -1,
            ),
            Flexible(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 14),
                child: Text(
                  monthLabel(month),
                  key: const Key('selected-month'),
                  style: Theme.of(context).textTheme.titleMedium,
                  textAlign: TextAlign.center,
                ),
              ),
            ),
            arrow('next-month', 'Next month', Icons.chevron_right_rounded, 1),
          ],
        ),
      ),
    );
  }
}

/// The hero card: the range first, then the band, then the single number.
class _RangeSummary extends StatelessWidget {
  const _RangeSummary({
    required this.result,
    required this.month,
    required this.wide,
  });

  final ForecastResult result;
  final YearMonth month;
  final bool wide;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final low = result.low;
    final high = result.high;

    return Container(
      padding: const EdgeInsets.fromLTRB(22, 20, 22, 22),
      decoration: BoxDecoration(
        color: Palette.forest,
        borderRadius: BorderRadius.circular(Radii.card),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (low != null && high != null) ...[
            if (wide)
              Text(
                '${monthLabel(month)}: likely between ${kes(low)} and ${kes(high)}',
                key: const Key('range-sentence'),
                style: textTheme.headlineSmall?.copyWith(color: Colors.white),
              )
            else ...[
              Row(
                children: [
                  const Icon(
                    Icons.insights_rounded,
                    size: 18,
                    color: Palette.onForestMuted,
                  ),
                  const SizedBox(width: 8),
                  Flexible(
                    child: Text(
                      'Likely to spend between',
                      style: textTheme.titleSmall?.copyWith(
                        color: Palette.onForestMuted,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 6),
              // One line, scaled down if it must be, so an amount is never
              // split across lines.
              FittedBox(
                fit: BoxFit.scaleDown,
                alignment: Alignment.centerLeft,
                child: Text(
                  '${kes(low)} and ${kes(high)}',
                  key: const Key('range-sentence'),
                  maxLines: 1,
                  style: textTheme.headlineSmall?.copyWith(
                    color: Colors.white,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ],
            const SizedBox(height: 18),
            RangeBand(low: low, high: high, point: result.estimatedTotal),
            const SizedBox(height: 12),
          ],
          Text(
            'Point estimate ${kes(result.estimatedTotal)}',
            key: const Key('point-estimate'),
            style: textTheme.titleMedium?.copyWith(
              color: Palette.onForestMuted,
              fontWeight: FontWeight.w500,
            ),
          ),
          const SizedBox(height: 16),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _Pill(
                icon: Icons.verified_outlined,
                text: 'Confidence ${result.confidence.toStringAsFixed(2)}',
              ),
              _Pill(
                icon: result.riskFlag == null
                    ? Icons.flag_outlined
                    : Icons.flag_rounded,
                text: 'Risk flag: ${riskLabel(result.riskFlag)}',
              ),
            ],
          ),
        ],
      ),
    );
  }
}

String riskLabel(RiskFlag? flag) => switch (flag) {
  null => 'none',
  RiskFlag.insufficientHistory => 'insufficient history',
  RiskFlag.volatile => 'volatile',
  RiskFlag.overspendRisk => 'overspend risk',
};

/// Table 4.9's client behaviour for the flags shown alongside a forecast.
String? riskNotice(RiskFlag? flag) => switch (flag) {
  // The flag describes the household's spending, not the forecast (FR-03 as
  // amended): the range is the same share of the estimate for everyone.
  RiskFlag.volatile =>
    'Caution: this household\'s spending varies a lot from month to month.',
  RiskFlag.overspendRisk =>
    'Overspend notice: this forecast is '
        'materially above the household\'s declared budget.',
  _ => null,
};

/// The likely range as a shaded band on a wider track, with the point
/// estimate marked inside it (wireframe 4.12b).
class RangeBand extends StatelessWidget {
  const RangeBand({
    super.key,
    required this.low,
    required this.high,
    required this.point,
  });

  final Decimal low;
  final Decimal high;
  final Decimal point;

  @override
  Widget build(BuildContext context) {
    // The track extends half the range's width either side, so the band sits
    // in the middle and its width reads as uncertainty, not as a scale from 0.
    final half = ((high - low) / Decimal.fromInt(2)).toDecimal(
      scaleOnInfinitePrecision: 2,
    );
    var start = low - half;
    if (start < Decimal.zero) start = Decimal.zero;
    final end = high + half;
    final span = end - start;
    double at(Decimal v) => fractionOf(v - start, span);

    return Semantics(
      label:
          'Likely range ${kes(low)} to ${kes(high)}, '
          'point estimate ${kes(point)}',
      excludeSemantics: true,
      child: SizedBox(
        height: 40,
        child: LayoutBuilder(
          builder: (context, constraints) {
            final w = constraints.maxWidth;
            return Stack(
              children: [
                Positioned(
                  left: 0,
                  right: 0,
                  top: 8,
                  height: 24,
                  child: Container(
                    decoration: BoxDecoration(
                      color: Colors.white.withValues(alpha: 0.10),
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                ),
                Positioned(
                  left: w * at(low),
                  width: w * (at(high) - at(low)),
                  top: 8,
                  height: 24,
                  child: Container(
                    key: const Key('range-band'),
                    decoration: BoxDecoration(
                      color: Palette.sageOnDark,
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                ),
                // The point estimate: a white mark with a 2 px forest ring,
                // so it stays distinct where it crosses the band.
                Positioned(
                  left: (w * at(point) - 4).clamp(0.0, w - 8),
                  width: 8,
                  top: 0,
                  bottom: 0,
                  child: Container(
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(4),
                      border: Border.all(color: Palette.forest, width: 2),
                    ),
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

/// A translucent pill on the hero card.
class _Pill extends StatelessWidget {
  const _Pill({required this.icon, required this.text});
  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 7),
    decoration: BoxDecoration(
      color: Colors.white.withValues(alpha: 0.12),
      borderRadius: BorderRadius.circular(100),
    ),
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 14, color: Colors.white),
        const SizedBox(width: 4),
        Flexible(
          child: Text(
            text,
            style: Theme.of(context).textTheme.labelLarge
                ?.copyWith(color: Colors.white),
          ),
        ),
      ],
    ),
  );
}

/// One destination in the Explore card: icon tile, label, detail, chevron.
class _LinkRow extends StatelessWidget {
  const _LinkRow({
    required this.icon,
    required this.label,
    required this.detail,
    required this.onTap,
    this.last = false,
  });

  final IconData icon;
  final String label;
  final String detail;
  final VoidCallback onTap;
  final bool last;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(Radii.tile),
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 12),
        decoration: BoxDecoration(
          border: last
              ? null
              : const Border(bottom: BorderSide(color: Palette.outline)),
        ),
        child: Row(
          children: [
            IconTile(icon),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(label, style: textTheme.titleSmall),
                  Text(
                    detail,
                    style: textTheme.bodySmall?.copyWith(color: Palette.muted),
                  ),
                ],
              ),
            ),
            const Icon(Icons.chevron_right_rounded, color: Palette.muted),
          ],
        ),
      ),
    );
  }
}

/// The three largest categories, as rows in a transaction-style list.
class _LargestCategories extends StatelessWidget {
  const _LargestCategories({required this.result, required this.onSeeAll});
  final ForecastResult result;
  final VoidCallback onSeeAll;

  @override
  Widget build(BuildContext context) {
    final rows = result.breakdownLargestFirst.take(3).toList();
    if (rows.isEmpty) return const SizedBox.shrink();
    final total = sum(result.breakdown.values);
    final textTheme = Theme.of(context).textTheme;

    return SectionCard(
      title: 'Largest categories',
      padding: const EdgeInsets.fromLTRB(20, 16, 12, 8),
      trailing: TextButton(
        onPressed: onSeeAll,
        child: const Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('See all'),
            SizedBox(width: 4),
            Icon(Icons.arrow_forward_rounded, size: 16),
          ],
        ),
      ),
      child: Column(
        children: [
          for (final (i, row) in rows.indexed)
            Container(
              padding: const EdgeInsets.fromLTRB(0, 10, 8, 10),
              decoration: BoxDecoration(
                border: i == rows.length - 1
                    ? null
                    : const Border(bottom: BorderSide(color: Palette.outline)),
              ),
              child: Row(
                children: [
                  IconTile(categoryIcon(row.key), dark: i == 0),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(row.key, style: textTheme.titleSmall),
                        Text(
                          '${percentOf(row.value, total)} of the estimate',
                          style: textTheme.bodySmall?.copyWith(
                            color: Palette.muted,
                          ),
                        ),
                      ],
                    ),
                  ),
                  Text(kes(row.value), style: textTheme.titleSmall),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

/// Wireframe 4.14f: breakdown and budget comparison side by side.
class _WidePanels extends StatefulWidget {
  const _WidePanels({required this.result});
  final ForecastResult result;

  @override
  State<_WidePanels> createState() => _WidePanelsState();
}

class _WidePanelsState extends State<_WidePanels> {
  @override
  void initState() {
    super.initState();
    // The phone layout loads the budget when its screen is opened; here the
    // panel is on screen at once, so it is loaded at once.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) context.read<ForecastController>().loadBudget();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: SectionCard(
            title: 'Category breakdown',
            child: BreakdownList(result: widget.result),
          ),
        ),
        const SizedBox(width: 16),
        const Expanded(
          child: SectionCard(
            title: 'Budget vs forecast',
            child: BudgetComparison(),
          ),
        ),
      ],
    );
  }
}

/// The three largest changes from usual, on the forecast itself. Loads the
/// insights for the selected month, and stays out of the way when it cannot:
/// no history, a failed request, or nothing loaded yet shows nothing.
class _WhatChangedPreview extends StatefulWidget {
  const _WhatChangedPreview({required this.onSeeAll});
  final VoidCallback onSeeAll;

  @override
  State<_WhatChangedPreview> createState() => _WhatChangedPreviewState();
}

class _WhatChangedPreviewState extends State<_WhatChangedPreview> {
  YearMonth? _requested;

  @override
  Widget build(BuildContext context) {
    final controller = context.watch<ForecastController>();
    final month = controller.month!;
    if (_requested != month) {
      _requested = month;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) context.read<ForecastController>().loadInsights();
      });
    }
    final insights = controller.insights;
    final usual = insights.value?.usual;
    if (insights.state != LoadState.loaded || usual == null) {
      return const SizedBox.shrink();
    }
    return WhatChangedCard(
      changes: controller.changesFromUsual(),
      usual: usual,
      month: month,
      forecastReady: true,
      limit: 3,
      onSeeAll: widget.onSeeAll,
    );
  }
}

/// Insights: what changed against usual spend, when in the month money goes
/// out, and the discretionary share — all from months before the selected one.
///
/// Laid out as a dashboard: the month control on top, three headline tiles,
/// then one card per question, each saying which months it is computed from.
/// Every chart's values are also written out beside or below it, so nothing
/// depends on hovering.
library;

import 'package:decimal/decimal.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../data/insights.dart';
import '../../data/models.dart';
import '../../state/forecast_controller.dart';
import '../format.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'dashboard_screen.dart';

class InsightsScreen extends StatefulWidget {
  const InsightsScreen({super.key, required this.wide});

  /// Desktop: tiles in a row, and the first two cards side by side.
  final bool wide;

  @override
  State<InsightsScreen> createState() => _InsightsScreenState();
}

class _InsightsScreenState extends State<InsightsScreen> {
  YearMonth? _requested;

  @override
  Widget build(BuildContext context) {
    final controller = context.watch<ForecastController>();
    final month = controller.month!;
    // The month control above changes the month; follow it.
    if (_requested != month) {
      _requested = month;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) context.read<ForecastController>().loadInsights();
      });
    }
    final insights = controller.insights;

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
      children: [
        MonthStepper(month: month),
        const SizedBox(height: 14),
        const SyntheticNotice(),
        const SizedBox(height: 14),
        switch (insights.state) {
          LoadState.idle || LoadState.loading => LoadingView(
            waking: insights.waking,
            what: 'insights',
          ),
          LoadState.error => ErrorView(
            error: insights.error!,
            onRetry: () => controller.loadInsights(force: true),
            onChangeHousehold: controller.changeHousehold,
          ),
          LoadState.loaded when insights.value!.isInsufficient =>
            InsufficientHistoryView(
              householdId: controller.householdId!,
              month: month,
            ),
          LoadState.loaded => _Loaded(
            result: insights.value!,
            changes: controller.changesFromUsual(),
            forecastReady: controller.forecast.state == LoadState.loaded,
            wide: widget.wide,
          ),
        },
      ],
    );
  }
}

class _Loaded extends StatelessWidget {
  const _Loaded({
    required this.result,
    required this.changes,
    required this.forecastReady,
    required this.wide,
  });

  final InsightsResult result;
  final List<CategoryChange> changes;
  final bool forecastReady;
  final bool wide;

  @override
  Widget build(BuildContext context) {
    final calendar = result.calendar!;
    final trend = result.discretionary!;

    final tiles = [
      _changeTile(),
      _calendarTile(calendar),
      _discretionaryTile(trend),
    ];
    final whatChanged = WhatChangedCard(
      changes: changes,
      usual: result.usual!,
      month: result.month,
      forecastReady: forecastReady,
    );
    final calendarCard = _CalendarCard(calendar: calendar);
    final trendCard = _DiscretionaryCard(trend: trend);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (wide)
          IntrinsicHeight(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                for (final (i, tile) in tiles.indexed) ...[
                  if (i > 0) const SizedBox(width: 12),
                  Expanded(child: tile),
                ],
              ],
            ),
          )
        else
          for (final tile in tiles) ...[tile, const SizedBox(height: 10)],
        const SizedBox(height: 16),
        if (wide) ...[
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(child: whatChanged),
              const SizedBox(width: 16),
              Expanded(child: calendarCard),
            ],
          ),
          const SizedBox(height: 16),
          trendCard,
        ] else ...[
          whatChanged,
          const SizedBox(height: 16),
          calendarCard,
          const SizedBox(height: 16),
          trendCard,
        ],
      ],
    );
  }

  Widget _changeTile() {
    if (!forecastReady || changes.isEmpty) {
      return const StatTile(
        icon: Icons.swap_vert_rounded,
        label: 'Biggest change from usual',
        value: '—',
        detail: 'Waiting for the forecast',
      );
    }
    final top = changes.first;
    return StatTile(
      icon: Icons.swap_vert_rounded,
      label: 'Biggest change from usual',
      value: signedKes(top.change),
      detail: top.category,
    );
  }

  Widget _calendarTile(SpendingCalendar calendar) {
    final busiest = [
      ...calendar.monthParts,
      ...calendar.weekdays,
    ].where((s) => s.standsOut).toList();
    if (busiest.isEmpty) {
      return const StatTile(
        icon: Icons.calendar_month_outlined,
        label: 'When the money goes out',
        value: 'Spread evenly',
        detail: 'No part of the month or week stands out',
      );
    }
    busiest.sort(
      (a, b) => (b.share - b.evenShare).compareTo(a.share - a.evenShare),
    );
    final top = busiest.first;
    return StatTile(
      icon: Icons.calendar_month_outlined,
      label: 'When the money goes out',
      value: top.label,
      detail:
          '${percent(top.share)} of spending; '
          'an even spread is ${percent(top.evenShare)}',
    );
  }

  Widget _discretionaryTile(DiscretionaryTrend trend) {
    final n = trend.months.length;
    final any = trend.monthsWithAny;
    final latest = trend.months.lastWhere(
      (m) => m.amount > Decimal.zero,
      orElse: () => trend.months.last,
    );
    return StatTile(
      icon: Icons.local_activity_outlined,
      label: 'Discretionary spending',
      value: any == 0 ? 'None' : '$any of $n months',
      detail: any == 0
          ? 'In the last $n months'
          : 'Latest ${monthLabel(latest.month)}: ${kes(latest.amount)}',
    );
  }
}

// ── what changed ──

/// The forecast against usual spend, one diverging bar per category.
///
/// Also used, with [limit], as the preview on the forecast dashboard.
class WhatChangedCard extends StatefulWidget {
  const WhatChangedCard({
    super.key,
    required this.changes,
    required this.usual,
    required this.month,
    required this.forecastReady,
    this.limit = 6,
    this.onSeeAll,
  });

  final List<CategoryChange> changes;
  final UsualSpend usual;
  final YearMonth month;
  final bool forecastReady;

  /// Rows shown before "Show all".
  final int limit;

  /// When set, a "See all" link replaces "Show all" (the dashboard preview).
  final VoidCallback? onSeeAll;

  @override
  State<WhatChangedCard> createState() => _WhatChangedCardState();
}

class _WhatChangedCardState extends State<WhatChangedCard> {
  bool _all = false;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final usualSpan = monthSpan(
      widget.usual.months.first,
      widget.usual.months.last,
    );
    final changes = widget.changes;
    final shown = _all ? changes : changes.take(widget.limit).toList();
    final scale = changes.fold(
      Decimal.zero,
      (m, c) => c.change.abs() > m ? c.change.abs() : m,
    );
    final totalChange = changes.fold(Decimal.zero, (t, c) => t + c.change);

    return SectionCard(
      key: const Key('what-changed'),
      title: 'What changed',
      trailing: widget.onSeeAll == null
          ? null
          : TextButton(
              onPressed: widget.onSeeAll,
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
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'The ${monthLabel(widget.month)} forecast against a typical '
            'month of $usualSpan (the median of the three)',
            style: textTheme.bodySmall?.copyWith(color: Palette.muted),
          ),
          const SizedBox(height: 14),
          if (!widget.forecastReady)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 12),
              child: Text(
                'Shown once the forecast has loaded.',
                style: TextStyle(color: Palette.muted),
              ),
            )
          else if (changes.isEmpty)
            const Text('Nothing to compare.')
          else ...[
            _TotalChange(change: totalChange),
            const SizedBox(height: 12),
            for (final c in shown) _ChangeRow(change: c, scale: scale),
            const SizedBox(height: 4),
            _ChangeLegend(),
            if (widget.onSeeAll == null && changes.length > widget.limit)
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton(
                  key: const Key('show-all-changes'),
                  onPressed: () => setState(() => _all = !_all),
                  child: Text(
                    _all
                        ? 'Show the largest ${widget.limit}'
                        : 'Show all ${changes.length} categories',
                  ),
                ),
              ),
          ],
        ],
      ),
    );
  }
}

class _TotalChange extends StatelessWidget {
  const _TotalChange({required this.change});
  final Decimal change;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
    decoration: BoxDecoration(
      color: Palette.cream,
      borderRadius: BorderRadius.circular(Radii.field),
    ),
    child: Row(
      children: [
        const Expanded(child: Text('All categories')),
        Text(
          signedKes(change),
          key: const Key('total-change'),
          style: Theme.of(context).textTheme.titleSmall,
        ),
      ],
    ),
  );
}

/// Category · bar either side of a zero line · signed amount.
class _ChangeRow extends StatelessWidget {
  const _ChangeRow({required this.change, required this.scale});
  final CategoryChange change;
  final Decimal scale;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final up = change.change > Decimal.zero;
    final fraction = fractionOf(change.change.abs(), scale);
    final description =
        '${change.category}: forecast ${kes(change.forecast)}, '
        'usual ${kes(change.usual)}, ${signedKes(change.change)}';

    return Tooltip(
      message: description,
      excludeFromSemantics: true,
      child: Semantics(
        label: description,
        excludeSemantics: true,
        child: Padding(
          key: Key('change-${change.category}'),
          padding: const EdgeInsets.symmetric(vertical: 6),
          child: Row(
            children: [
              SizedBox(
                width: 104,
                child: Text(
                  change.category,
                  style: textTheme.bodyMedium,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: SizedBox(
                  height: 18,
                  child: LayoutBuilder(
                    builder: (context, box) {
                      final half = box.maxWidth / 2;
                      final length = (half * fraction).clamp(
                        change.change == Decimal.zero ? 0.0 : 2.0,
                        half,
                      );
                      return Stack(
                        children: [
                          Positioned(
                            left: half - 0.5,
                            top: 0,
                            bottom: 0,
                            width: 1,
                            child: const ColoredBox(color: Palette.zeroLine),
                          ),
                          Positioned(
                            left: up ? half + 0.5 : half - 0.5 - length,
                            width: length,
                            top: 4,
                            bottom: 4,
                            child: Container(
                              decoration: BoxDecoration(
                                color: up ? Palette.above : Palette.below,
                                // Rounded at the data end, square at zero.
                                borderRadius: up
                                    ? const BorderRadius.horizontal(
                                        right: Radius.circular(4),
                                      )
                                    : const BorderRadius.horizontal(
                                        left: Radius.circular(4),
                                      ),
                              ),
                            ),
                          ),
                        ],
                      );
                    },
                  ),
                ),
              ),
              const SizedBox(width: 8),
              SizedBox(
                width: 92,
                child: Text(
                  signedKes(change.change),
                  textAlign: TextAlign.right,
                  style: textTheme.labelLarge,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ChangeLegend extends StatelessWidget {
  @override
  Widget build(BuildContext context) => const Wrap(
    spacing: 18,
    runSpacing: 6,
    children: [
      _Swatch(color: Palette.above, label: 'above a typical month'),
      _Swatch(color: Palette.below, label: 'below a typical month'),
    ],
  );
}

// ── the spending calendar ──

class _CalendarCard extends StatelessWidget {
  const _CalendarCard({required this.calendar});
  final SpendingCalendar calendar;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final months = calendar.months;
    final standsOut = [
      ...calendar.monthParts,
      ...calendar.weekdays,
    ].where((s) => s.standsOut).toList();

    final headline = standsOut.isEmpty
        ? 'Spending is spread evenly through the month and the week.'
        : '${standsOut.map((s) => s.label).join(' and ')} '
              '${standsOut.length == 1 ? 'takes' : 'take'} more than an even '
              'share of spending.';

    return SectionCard(
      key: const Key('spending-calendar'),
      title: 'Spending calendar',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'Share of spending, ${monthSpan(months.first, months.last)} '
            '(${months.length} months)',
            style: textTheme.bodySmall?.copyWith(color: Palette.muted),
          ),
          const SizedBox(height: 12),
          Text(
            headline,
            key: const Key('calendar-headline'),
            style: textTheme.titleSmall,
          ),
          const SizedBox(height: 16),
          Text('Through the month', style: textTheme.labelLarge),
          const SizedBox(height: 6),
          _ShareRows(slots: calendar.monthParts),
          const SizedBox(height: 16),
          Text('Through the week', style: textTheme.labelLarge),
          const SizedBox(height: 6),
          _ShareRows(slots: calendar.weekdays),
          const SizedBox(height: 10),
          const Wrap(
            spacing: 18,
            runSpacing: 6,
            children: [
              _Swatch(color: Palette.forest, label: 'stands out'),
              _Swatch(color: Palette.sage, label: 'within normal variation'),
              _Tick(label: 'even spread'),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            '"Stands out" means more than an even share by a margin that '
            'month-to-month variation does not explain.',
            style: textTheme.bodySmall?.copyWith(color: Palette.muted),
          ),
        ],
      ),
    );
  }
}

/// One row per slot: label, bar with an even-spread tick, share.
class _ShareRows extends StatelessWidget {
  const _ShareRows({required this.slots});
  final List<CalendarSlot> slots;

  @override
  Widget build(BuildContext context) {
    final scale = slots
        .map((s) => s.share > s.evenShare ? s.share : s.evenShare)
        .fold(0.0, (a, b) => a > b ? a : b);
    final textTheme = Theme.of(context).textTheme;

    return Column(
      children: [
        for (final s in slots)
          Tooltip(
            message:
                '${s.label}: ${percent(s.share)} of spending, about '
                '${kes(s.averageAmount)} a month; an even spread is '
                '${percent(s.evenShare)}',
            excludeFromSemantics: true,
            child: Semantics(
              label:
                  '${s.label}: ${percent(s.share)}, even spread '
                  '${percent(s.evenShare)}'
                  '${s.standsOut ? ', stands out' : ''}',
              excludeSemantics: true,
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Row(
                  children: [
                    SizedBox(
                      width: 112,
                      child: Text(s.label, style: textTheme.bodyMedium),
                    ),
                    Expanded(
                      child: SizedBox(
                        height: 18,
                        child: LayoutBuilder(
                          builder: (context, box) {
                            final w = box.maxWidth;
                            double at(double v) =>
                                scale <= 0 ? 0 : w * (v / scale).clamp(0, 1);
                            return Stack(
                              children: [
                                Positioned(
                                  left: 0,
                                  top: 5,
                                  bottom: 5,
                                  width: at(s.share).clamp(2.0, w),
                                  child: Container(
                                    decoration: BoxDecoration(
                                      color: s.standsOut
                                          ? Palette.forest
                                          : Palette.sage,
                                      borderRadius:
                                          const BorderRadius.horizontal(
                                            right: Radius.circular(4),
                                          ),
                                    ),
                                  ),
                                ),
                                // Even spread: a 2 px ink tick across the bar.
                                Positioned(
                                  left: (at(s.evenShare) - 1).clamp(0, w - 2),
                                  top: 0,
                                  bottom: 0,
                                  width: 2,
                                  child: const ColoredBox(color: Palette.ink),
                                ),
                              ],
                            );
                          },
                        ),
                      ),
                    ),
                    SizedBox(
                      width: 48,
                      child: Text(
                        percent(s.share),
                        textAlign: TextAlign.right,
                        style: textTheme.labelLarge,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
      ],
    );
  }
}

// ── the discretionary trend ──

class _DiscretionaryCard extends StatelessWidget {
  const _DiscretionaryCard({required this.trend});
  final DiscretionaryTrend trend;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final months = trend.months;
    final withAny = months.where((m) => m.amount > Decimal.zero).toList();
    final peak = months.fold(0.0, (a, m) => m.share > a ? m.share : a);
    final names = trend.categories;
    final list = '${names.take(names.length - 1).join(', ')} and ${names.last}';

    return SectionCard(
      key: const Key('discretionary'),
      title: 'Discretionary share',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            '$list, as a share of each month\'s spending, '
            '${monthSpan(months.first.month, months.last.month)}',
            style: textTheme.bodySmall?.copyWith(color: Palette.muted),
          ),
          const SizedBox(height: 16),
          SizedBox(
            height: 150,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                for (final m in months)
                  Expanded(
                    child: _MonthColumn(
                      month: m,
                      scale: peak,
                      labelled: peak > 0 && m.share == peak,
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(height: 14),
          if (withAny.isEmpty)
            Text(
              'No spending in these categories in the last '
              '${months.length} months.',
              key: const Key('no-discretionary'),
              style: textTheme.bodyMedium,
            )
          else
            for (final m in withAny) _DiscretionaryRow(month: m),
          const SizedBox(height: 10),
          Text(
            'A grouping this project chose: spending in these categories is '
            'optional and can change quickly. The figures describe what was '
            'recorded; they are not a judgement of the household.',
            style: textTheme.bodySmall?.copyWith(color: Palette.muted),
          ),
        ],
      ),
    );
  }
}

class _MonthColumn extends StatelessWidget {
  const _MonthColumn({
    required this.month,
    required this.scale,
    required this.labelled,
  });

  final DiscretionaryMonth month;
  final double scale;

  /// The tallest column carries its value; the rest use the tooltip and the
  /// rows below.
  final bool labelled;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final description =
        '${monthLabel(month.month)}: ${percent(month.share)}, '
        '${kes(month.amount)} of ${kes(month.total)}';
    final fraction = scale <= 0 ? 0.0 : month.share / scale;

    return Tooltip(
      message: description,
      excludeFromSemantics: true,
      child: Semantics(
        label: description,
        excludeSemantics: true,
        child: Column(
          children: [
            SizedBox(
              height: 18,
              child: labelled
                  ? FittedBox(
                      child: Text(
                        percent(month.share),
                        style: textTheme.labelSmall?.copyWith(
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    )
                  : null,
            ),
            Expanded(
              child: Align(
                alignment: Alignment.bottomCenter,
                child: month.share == 0
                    // A zero month is a short baseline tick, not an absence.
                    ? Container(width: 14, height: 2, color: Palette.zeroLine)
                    : FractionallySizedBox(
                        heightFactor: fraction.clamp(0.02, 1.0),
                        child: Container(
                          width: 14,
                          decoration: const BoxDecoration(
                            color: Palette.forest,
                            borderRadius: BorderRadius.vertical(
                              top: Radius.circular(4),
                            ),
                          ),
                        ),
                      ),
              ),
            ),
            const SizedBox(height: 6),
            FittedBox(
              child: Text(
                monthShort(month.month),
                style: textTheme.labelSmall?.copyWith(color: Palette.muted),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _DiscretionaryRow extends StatelessWidget {
  const _DiscretionaryRow({required this.month});
  final DiscretionaryMonth month;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final parts = [
      for (final e in month.byCategory.entries)
        if (e.value > Decimal.zero) e.key,
    ];
    return Container(
      key: Key('discretionary-${month.month}'),
      padding: const EdgeInsets.symmetric(vertical: 10),
      decoration: const BoxDecoration(
        border: Border(top: BorderSide(color: Palette.outline)),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(monthLabel(month.month), style: textTheme.titleSmall),
                Text(
                  parts.join(', '),
                  style: textTheme.bodySmall?.copyWith(color: Palette.muted),
                ),
              ],
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(kes(month.amount), style: textTheme.titleSmall),
              Text(
                '${percent(month.share)} of the month',
                style: textTheme.bodySmall?.copyWith(color: Palette.muted),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

// ── legend pieces ──

class _Swatch extends StatelessWidget {
  const _Swatch({required this.color, required this.label});
  final Color color;
  final String label;

  @override
  Widget build(BuildContext context) => Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      Container(
        width: 14,
        height: 10,
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(3),
        ),
      ),
      const SizedBox(width: 6),
      Flexible(
        child: Text(label, style: Theme.of(context).textTheme.bodySmall),
      ),
    ],
  );
}

class _Tick extends StatelessWidget {
  const _Tick({required this.label});
  final String label;

  @override
  Widget build(BuildContext context) => Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      Container(width: 2, height: 14, color: Palette.ink),
      const SizedBox(width: 6),
      Flexible(
        child: Text(label, style: Theme.of(context).textTheme.bodySmall),
      ),
    ],
  );
}

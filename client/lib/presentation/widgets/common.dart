/// Widgets shared by every screen: the synthetic notice, the loading, error
/// and insufficient-history views, cards, banners and a labelled bar.
library;

import 'package:flutter/material.dart';

import '../../data/api_exception.dart';
import '../../data/models.dart';
import '../format.dart';
import '../theme.dart';

/// FR-16: on every forecast screen.
class SyntheticNotice extends StatelessWidget {
  const SyntheticNotice({super.key, this.onDark = false});

  /// Drawn on the forest background of the household screen.
  final bool onDark;

  static const text = 'All figures are synthetic';

  @override
  Widget build(BuildContext context) {
    final ink = onDark ? Colors.white : Palette.forest;
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: onDark ? Colors.white.withValues(alpha: 0.12) : Palette.mint,
          borderRadius: BorderRadius.circular(100),
        ),
        child: Semantics(
          label:
              'Notice: all figures are synthetic, generated test data, '
              'not real household spending.',
          excludeSemantics: true,
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.science_outlined, size: 16, color: ink),
              const SizedBox(width: 6),
              Flexible(
                child: Text(
                  text,
                  style: Theme.of(context).textTheme.labelMedium
                      ?.copyWith(color: ink, fontStyle: FontStyle.italic),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// IR-04: a spinner, and after 5 seconds an explanation that the service is
/// waking up — Render's free plan takes about 50 seconds to start.
class LoadingView extends StatelessWidget {
  const LoadingView({super.key, required this.waking, this.what = 'forecast'});

  final bool waking;
  final String what;

  static const wakingText = 'The service is waking up';

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 40),
      child: Column(
        children: [
          const CircularProgressIndicator(),
          const SizedBox(height: 16),
          if (waking) ...[
            Text(wakingText, style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 4),
            const Text(
              'It sleeps when unused and can take up to a minute to start. '
              'Please keep this screen open.',
              textAlign: TextAlign.center,
              style: TextStyle(color: Palette.muted),
            ),
          ] else
            Text(
              'Loading $what…',
              style: const TextStyle(color: Palette.muted),
            ),
        ],
      ),
    );
  }
}

/// A coloured, rounded message with a leading icon: notices, summaries and
/// the error and insufficient-history views all share this shape.
class NoticeBanner extends StatelessWidget {
  const NoticeBanner({
    super.key,
    required this.icon,
    required this.background,
    required this.foreground,
    required this.child,
  });

  final IconData icon;
  final Color background;
  final Color foreground;
  final Widget child;

  @override
  Widget build(BuildContext context) => Container(
    width: double.infinity,
    padding: const EdgeInsets.all(16),
    decoration: BoxDecoration(
      color: background,
      borderRadius: BorderRadius.circular(Radii.tile + 2),
    ),
    child: Row(
      children: [
        Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: 0.7),
            shape: BoxShape.circle,
          ),
          child: Icon(icon, color: foreground, size: 22),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: DefaultTextStyle.merge(
            style: TextStyle(color: foreground),
            child: child,
          ),
        ),
      ],
    ),
  );
}

/// FR-15: a clear message and a retry action for every failure.
class ErrorView extends StatelessWidget {
  const ErrorView({
    super.key,
    required this.error,
    required this.onRetry,
    this.onChangeHousehold,
  });

  final ApiException error;
  final VoidCallback onRetry;

  /// Offered for a rejected request, so the user can correct the input.
  final VoidCallback? onChangeHousehold;

  static String titleFor(ApiErrorKind kind) => switch (kind) {
    ApiErrorKind.timeout => 'The service did not answer in time',
    ApiErrorKind.network => 'Cannot reach the service',
    ApiErrorKind.validation => 'The request was rejected',
    ApiErrorKind.server => 'The service had a problem',
  };

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 16),
      child: NoticeBanner(
        icon: Icons.cloud_off_outlined,
        background: Palette.overBg,
        foreground: Palette.over,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              titleFor(error.kind),
              style: Theme.of(context).textTheme.titleMedium
                  ?.copyWith(color: Palette.over),
            ),
            const SizedBox(height: 6),
            Text(error.message, style: const TextStyle(color: Palette.ink)),
            const SizedBox(height: 14),
            Wrap(
              spacing: 12,
              runSpacing: 8,
              children: [
                FilledButton.icon(
                  onPressed: onRetry,
                  icon: const Icon(Icons.refresh),
                  label: const Text('Retry'),
                ),
                if (error.kind == ApiErrorKind.validation &&
                    onChangeHousehold != null)
                  OutlinedButton(
                    onPressed: onChangeHousehold,
                    style: OutlinedButton.styleFrom(
                      minimumSize: const Size(64, 52),
                    ),
                    child: const Text('Change household'),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// FR-06: an explanation, not an error. Unknown households and those with
/// fewer than three months of history both arrive as insufficient_history.
class InsufficientHistoryView extends StatelessWidget {
  const InsufficientHistoryView({
    super.key,
    required this.householdId,
    required this.month,
  });

  final String householdId;
  final YearMonth month;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 16),
      child: NoticeBanner(
        icon: Icons.hourglass_empty_rounded,
        background: Palette.mint,
        foreground: Palette.forest,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'No forecast can be made yet',
              style: Theme.of(context).textTheme.titleMedium
                  ?.copyWith(color: Palette.forest),
            ),
            const SizedBox(height: 6),
            Text(
              'There are fewer than three months of spending history for '
              '$householdId before ${monthLabel(month)}, or the household is '
              'not known to the service. A forecast needs at least three '
              'months. Check the household ID, or try a later month.',
              style: const TextStyle(color: Palette.ink),
            ),
          ],
        ),
      ),
    );
  }
}

/// "h015  |  October 2026" — the context line under each screen title.
class ContextLine extends StatelessWidget {
  const ContextLine(this.text, {super.key});
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 12),
    child: Text(
      text,
      style: Theme.of(context).textTheme.titleMedium
          ?.copyWith(color: Palette.muted),
    ),
  );
}

/// A white rounded card with an optional heading row.
class SectionCard extends StatelessWidget {
  const SectionCard({
    super.key,
    this.title,
    this.trailing,
    required this.child,
    this.padding = const EdgeInsets.all(20),
  });

  final String? title;
  final Widget? trailing;
  final Widget child;
  final EdgeInsets padding;

  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: padding,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (title != null) ...[
            Row(
              children: [
                Expanded(
                  child: Text(
                    title!,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                ?trailing,
              ],
            ),
            const SizedBox(height: 14),
          ],
          child,
        ],
      ),
    ),
  );
}

/// A rounded-square tile holding an icon, as in a transaction list.
class IconTile extends StatelessWidget {
  const IconTile(this.icon, {super.key, this.size = 44, this.dark = false});

  final IconData icon;
  final double size;

  /// Forest tile with a white icon, for the one item a row is about.
  final bool dark;

  @override
  Widget build(BuildContext context) => Container(
    width: size,
    height: size,
    decoration: BoxDecoration(
      color: dark ? Palette.forest : Palette.mint,
      borderRadius: BorderRadius.circular(size * 0.32),
    ),
    child: Icon(
      icon,
      size: size * 0.5,
      color: dark ? Colors.white : Palette.forest,
    ),
  );
}

/// The icon for a spending category. Unknown categories get a generic one;
/// the name beside it always carries the identity.
IconData categoryIcon(String category) => switch (category.toLowerCase()) {
  'rent' => Icons.home_outlined,
  'groceries' => Icons.shopping_basket_outlined,
  'school fees' => Icons.school_outlined,
  'transport' => Icons.directions_bus_outlined,
  'household help' => Icons.cleaning_services_outlined,
  'utilities' => Icons.bolt_outlined,
  'savings' => Icons.savings_outlined,
  'airtime and data' => Icons.smartphone_outlined,
  'medical' => Icons.medical_services_outlined,
  'entertainment' => Icons.movie_outlined,
  'electronics upgrade' => Icons.devices_outlined,
  'crypto purchase' => Icons.currency_bitcoin,
  'cash advance' => Icons.payments_outlined,
  'foreign transfer' => Icons.public,
  'gambling' => Icons.casino_outlined,
  'jewellery' => Icons.diamond_outlined,
  'luxury goods' => Icons.shopping_bag_outlined,
  _ => Icons.category_outlined,
};

/// A horizontal bar [fraction] (0..1) of the available width, with a 4 px
/// rounded data end and a square end at the baseline.
class FractionBar extends StatelessWidget {
  const FractionBar({
    super.key,
    required this.fraction,
    required this.color,
    this.height = 10,
  });

  final double fraction;
  final Color color;
  final double height;

  @override
  Widget build(BuildContext context) => Align(
    alignment: Alignment.centerLeft,
    child: FractionallySizedBox(
      widthFactor: fraction == 0 ? 0.004 : fraction,
      child: Container(
        height: height,
        decoration: BoxDecoration(
          color: color,
          borderRadius: const BorderRadius.horizontal(
            right: Radius.circular(4),
          ),
        ),
      ),
    ),
  );
}

/// A headline figure: label, value, and one line of context. Neutral by
/// design: nothing here is coloured as good or bad.
class StatTile extends StatelessWidget {
  const StatTile({
    super.key,
    required this.icon,
    required this.label,
    required this.value,
    required this.detail,
  });

  final IconData icon;
  final String label;
  final String value;
  final String detail;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            IconTile(icon, size: 40),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    label,
                    style: textTheme.bodySmall?.copyWith(color: Palette.muted),
                  ),
                  const SizedBox(height: 2),
                  Text(value, style: textTheme.titleLarge),
                  const SizedBox(height: 2),
                  Text(
                    detail,
                    style: textTheme.bodySmall?.copyWith(color: Palette.muted),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

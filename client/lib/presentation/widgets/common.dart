/// Widgets shared by every screen: the synthetic notice, the loading, error
/// and insufficient-history views, and a labelled bar.
library;

import 'package:flutter/material.dart';

import '../../data/api_exception.dart';
import '../../data/models.dart';
import '../format.dart';

/// FR-16: on every forecast screen.
class SyntheticNotice extends StatelessWidget {
  const SyntheticNotice({super.key});

  static const text = 'All figures are synthetic';

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerHighest,
        border: Border.all(color: scheme.outline),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Semantics(
        label:
            'Notice: all figures are synthetic, generated test data, '
            'not real household spending.',
        excludeSemantics: true,
        child: const Text(text, style: TextStyle(fontStyle: FontStyle.italic)),
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
      padding: const EdgeInsets.symmetric(vertical: 32),
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
            ),
          ] else
            Text('Loading $what…'),
        ],
      ),
    );
  }
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
    final scheme = Theme.of(context).colorScheme;
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.symmetric(vertical: 16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: scheme.errorContainer,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            titleFor(error.kind),
            style: Theme.of(context).textTheme.titleMedium
                ?.copyWith(color: scheme.onErrorContainer),
          ),
          const SizedBox(height: 6),
          Text(error.message, style: TextStyle(color: scheme.onErrorContainer)),
          const SizedBox(height: 12),
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
                  child: const Text('Change household'),
                ),
            ],
          ),
        ],
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
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.symmetric(vertical: 16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.secondaryContainer,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'No forecast can be made yet',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 6),
          Text(
            'There are fewer than three months of spending history for '
            '$householdId before ${monthLabel(month)}, or the household is '
            'not known to the service. A forecast needs at least three '
            'months. Check the household ID, or try a later month.',
          ),
        ],
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
          ?.copyWith(color: Theme.of(context).colorScheme.onSurfaceVariant),
    ),
  );
}

/// A horizontal bar [fraction] (0..1) of the available width.
class FractionBar extends StatelessWidget {
  const FractionBar({
    super.key,
    required this.fraction,
    required this.color,
    this.height = 14,
  });

  final double fraction;
  final Color color;
  final double height;

  @override
  Widget build(BuildContext context) => Align(
    alignment: Alignment.centerLeft,
    child: FractionallySizedBox(
      widthFactor: fraction == 0 ? 0.004 : fraction,
      child: Container(height: height, color: color),
    ),
  );
}

/// Sign up or log in to a demo household (data/demo.dart).
///
/// A name and a PIN, so a presenter can come back to the household they
/// made. It is not authentication, and the screen says so.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../state/demo_controller.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'demo_budget_screen.dart';

class DemoLoginScreen extends StatefulWidget {
  const DemoLoginScreen({super.key});

  @override
  State<DemoLoginScreen> createState() => _DemoLoginScreenState();
}

class _DemoLoginScreenState extends State<DemoLoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _pin = TextEditingController();
  bool _signingUp = true;

  @override
  void dispose() {
    _name.dispose();
    _pin.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    final demo = context.read<DemoController>();
    final ok = _signingUp
        ? await demo.signup(_name.text, _pin.text)
        : await demo.login(_name.text, _pin.text);
    if (!ok || !mounted) return;

    if (demo.household!.hasBudget) {
      Navigator.of(context).pop();
      await demo.enter();
    } else {
      // A new household declares its budget before anything else.
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(
          builder: (_) => const DemoBudgetScreen(onboarding: true),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final demo = context.watch<DemoController>();
    final textTheme = Theme.of(context).textTheme;

    return Scaffold(
      backgroundColor: Palette.forest,
      appBar: AppBar(
        backgroundColor: Palette.forest,
        foregroundColor: Colors.white,
        title: const Text('Demo household'),
      ),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 520),
            child: ListView(
              padding: const EdgeInsets.fromLTRB(24, 8, 24, 32),
              children: [
                Text(
                  _signingUp
                      ? 'Start a household from nothing'
                      : 'Back to your household',
                  style: textTheme.headlineSmall?.copyWith(
                    color: Colors.white,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 10),
                Text(
                  'Declare a budget, then build up spending month by month '
                  'and watch the forecast appear. For demonstrations only: '
                  'the PIN is not a password, and households are cleared '
                  'when the service restarts.',
                  style: textTheme.bodyLarge?.copyWith(
                    color: Palette.onForestMuted,
                  ),
                ),
                const SizedBox(height: 18),
                const SyntheticNotice(onDark: true),
                const SizedBox(height: 28),
                SegmentedButton<bool>(
                  key: const Key('demo-mode'),
                  segments: const [
                    ButtonSegment(value: true, label: Text('Sign up')),
                    ButtonSegment(value: false, label: Text('Log in')),
                  ],
                  selected: {_signingUp},
                  onSelectionChanged: (s) =>
                      setState(() => _signingUp = s.first),
                  style: SegmentedButton.styleFrom(
                    foregroundColor: Colors.white,
                    selectedForegroundColor: Palette.forest,
                    selectedBackgroundColor: Colors.white,
                    side: const BorderSide(color: Palette.onForestMuted),
                  ),
                ),
                const SizedBox(height: 24),
                Form(
                  key: _formKey,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const _Label('Household name'),
                      TextFormField(
                        key: const Key('demo-name'),
                        controller: _name,
                        maxLength: 40,
                        decoration: const InputDecoration(
                          hintText: 'e.g. The Otieno family',
                          prefixIcon: Icon(Icons.home_outlined),
                          counterText: '',
                          errorStyle: TextStyle(color: _errorOnForest),
                        ),
                        textInputAction: TextInputAction.next,
                        validator: (v) => (v ?? '').trim().isEmpty
                            ? 'Enter a name for the household'
                            : null,
                      ),
                      const SizedBox(height: 18),
                      const _Label('PIN'),
                      TextFormField(
                        key: const Key('demo-pin'),
                        controller: _pin,
                        obscureText: true,
                        keyboardType: TextInputType.number,
                        inputFormatters: [
                          FilteringTextInputFormatter.digitsOnly,
                          LengthLimitingTextInputFormatter(8),
                        ],
                        decoration: const InputDecoration(
                          hintText: '4 to 8 digits',
                          prefixIcon: Icon(Icons.pin_outlined),
                          errorStyle: TextStyle(color: _errorOnForest),
                        ),
                        textInputAction: TextInputAction.go,
                        onFieldSubmitted: (_) => _submit(),
                        validator: (v) => RegExp(r'^\d{4,8}$').hasMatch(v ?? '')
                            ? null
                            : 'Use 4 to 8 digits',
                      ),
                    ],
                  ),
                ),
                if (demo.error case final error?) ...[
                  const SizedBox(height: 16),
                  Text(
                    error.message,
                    key: const Key('demo-error'),
                    style: const TextStyle(color: _errorOnForest),
                  ),
                ],
                const SizedBox(height: 28),
                FilledButton(
                  key: const Key('demo-submit'),
                  onPressed: demo.busy ? null : _submit,
                  style: FilledButton.styleFrom(
                    backgroundColor: Colors.white,
                    foregroundColor: Palette.forest,
                    minimumSize: const Size.fromHeight(56),
                  ),
                  child: demo.busy
                      ? const SizedBox.square(
                          dimension: 22,
                          child: CircularProgressIndicator(strokeWidth: 2.5),
                        )
                      : Text(_signingUp ? 'Create household' : 'Log in'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// As on the household screen: validation messages sit on the forest.
const _errorOnForest = Color(0xFFFFD3C2);

class _Label extends StatelessWidget {
  const _Label(this.text);
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

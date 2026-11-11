/// The app's look: forest green on warm cream, white rounded cards, Poppins.
///
/// Every colour a screen uses comes from [Palette], so the contrast pairs
/// below are the only ones to check. Measured (WCAG relative luminance):
/// ink on cream 14.7:1, muted on cream 5.3:1, white on forest 12.2:1,
/// onForestMuted on forest 8.0:1; marks against their surface are all at
/// least 3:1 (sage bar on white 3.2:1, band on forest 6.8:1).
library;

import 'package:flutter/material.dart';

abstract final class Palette {
  /// The brand colour: the hero card, primary buttons, the forecast mark.
  static const forest = Color(0xFF1F3B2D);
  static const forestDeep = Color(0xFF16291F);

  /// The second mark colour (budget bars, unselected months) on white.
  static const sage = Color(0xFF6E9A79);

  /// Marks drawn on the forest background (the likely-range band).
  static const sageOnDark = Color(0xFFA8CBA9);

  /// Quiet tinted fills: icon tiles, the synthetic notice, selected pills.
  static const mint = Color(0xFFE3EDE0);

  static const cream = Color(0xFFF3F1EA);
  static const surface = Color(0xFFFFFFFF);
  static const outline = Color(0xFFE6E4DC);

  static const ink = Color(0xFF18201B);
  static const muted = Color(0xFF5B665E);
  static const onForestMuted = Color(0xFFC5D6C8);

  /// Status: over budget. Always shipped with the word "over" or an icon.
  static const over = Color(0xFFA9461F);
  static const overBg = Color(0xFFF7E4DA);

  /// The diverging pair for "vs usual": warm above, cool below, meeting at a
  /// neutral zero line. Neither is a status colour, and the signed amount is
  /// always written beside the bar, so direction never rests on colour.
  /// On white: above 4.1:1, below 5.4:1. OKLab distance between them 20.5
  /// (17 or more under simulated red-green colour blindness); above sits 11.2
  /// from [over].
  static const above = Color(0xFFA6741A);
  static const below = Color(0xFF3F6F92);
  static const zeroLine = Color(0xFFB9B7AE);

  /// Status: caution notices (volatile, overspend).
  static const cautionBg = Color(0xFFF4EAD0);
  static const cautionInk = Color(0xFF5A430E);
}

abstract final class Radii {
  static const card = 24.0;
  static const tile = 16.0;
  static const field = 14.0;
}

ThemeData appTheme() {
  final scheme =
      ColorScheme.fromSeed(
        seedColor: Palette.forest,
        brightness: Brightness.light,
      ).copyWith(
        primary: Palette.forest,
        onPrimary: Colors.white,
        primaryContainer: Palette.mint,
        onPrimaryContainer: Palette.forest,
        secondary: Palette.sage,
        surface: Palette.surface,
        onSurface: Palette.ink,
        onSurfaceVariant: Palette.muted,
        surfaceContainerLowest: Palette.surface,
        surfaceContainerLow: Palette.cream,
        surfaceContainer: Palette.cream,
        surfaceContainerHighest: Palette.mint,
        outline: Palette.sage,
        outlineVariant: Palette.outline,
        tertiaryContainer: Palette.cautionBg,
        onTertiaryContainer: Palette.cautionInk,
        errorContainer: Palette.overBg,
        onErrorContainer: Palette.over,
      );

  final base = ThemeData(
    colorScheme: scheme,
    useMaterial3: true,
    fontFamily: 'Poppins',
  );
  final text = base.textTheme.apply(
    bodyColor: Palette.ink,
    displayColor: Palette.ink,
  );
  final stadium = WidgetStatePropertyAll<OutlinedBorder>(
    RoundedRectangleBorder(borderRadius: BorderRadius.circular(100)),
  );

  return base.copyWith(
    scaffoldBackgroundColor: Palette.cream,
    textTheme: text.copyWith(
      headlineSmall: text.headlineSmall?.copyWith(fontWeight: FontWeight.w600),
      titleLarge: text.titleLarge?.copyWith(fontWeight: FontWeight.w600),
      titleMedium: text.titleMedium?.copyWith(fontWeight: FontWeight.w600),
      titleSmall: text.titleSmall?.copyWith(fontWeight: FontWeight.w600),
    ),
    appBarTheme: AppBarTheme(
      backgroundColor: Palette.cream,
      surfaceTintColor: Colors.transparent,
      foregroundColor: Palette.ink,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: true,
      titleTextStyle: text.titleLarge?.copyWith(fontWeight: FontWeight.w600),
    ),
    cardTheme: CardThemeData(
      color: Palette.surface,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(Radii.card),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: ButtonStyle(
        shape: stadium,
        minimumSize: const WidgetStatePropertyAll(Size(64, 52)),
        textStyle: WidgetStatePropertyAll(
          text.titleSmall?.copyWith(fontWeight: FontWeight.w600),
        ),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: ButtonStyle(
        shape: stadium,
        side: const WidgetStatePropertyAll(BorderSide(color: Palette.sage)),
      ),
    ),
    textButtonTheme: TextButtonThemeData(style: ButtonStyle(shape: stadium)),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: Palette.surface,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(Radii.field),
        borderSide: const BorderSide(color: Palette.outline),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(Radii.field),
        borderSide: const BorderSide(color: Palette.outline),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(Radii.field),
        borderSide: const BorderSide(color: Palette.forest, width: 2),
      ),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: Palette.surface,
      surfaceTintColor: Colors.transparent,
      indicatorColor: Palette.forest,
      elevation: 0,
      height: 72,
      iconTheme: WidgetStateProperty.resolveWith(
        (states) => IconThemeData(
          color: states.contains(WidgetState.selected)
              ? Colors.white
              : Palette.muted,
        ),
      ),
      labelTextStyle: WidgetStateProperty.resolveWith(
        (states) => text.labelMedium?.copyWith(
          color: states.contains(WidgetState.selected)
              ? Palette.forest
              : Palette.muted,
          fontWeight: states.contains(WidgetState.selected)
              ? FontWeight.w600
              : FontWeight.w500,
        ),
      ),
    ),
    dividerTheme: const DividerThemeData(color: Palette.outline, space: 1),
    progressIndicatorTheme: const ProgressIndicatorThemeData(
      color: Palette.forest,
    ),
    tooltipTheme: TooltipThemeData(
      decoration: BoxDecoration(
        color: Palette.forest,
        borderRadius: BorderRadius.circular(10),
      ),
      textStyle: text.labelMedium?.copyWith(color: Colors.white),
    ),
  );
}

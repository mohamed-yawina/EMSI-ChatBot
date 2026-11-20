import 'package:flutter/material.dart';

class AppTheme {
  static const Color green = Color(0xFF087F46);
  static const Color greenDark = Color(0xFF075B37);
  static const Color lightBackground = Color(0xFFF7FAF8);
  static const Color lightGreen = Color(0xFFE8F5EC);
  static const Color text = Color(0xFF172B22);

  static ThemeData light() {
    final scheme =
        ColorScheme.fromSeed(
          seedColor: green,
          brightness: Brightness.light,
        ).copyWith(
          primary: green,
          onPrimary: Colors.white,
          primaryContainer: lightGreen,
          onPrimaryContainer: greenDark,
          secondary: greenDark,
          onSecondary: Colors.white,
          secondaryContainer: const Color(0xFFD8EBDD),
          onSecondaryContainer: text,
          surface: Colors.white,
          onSurface: text,
          surfaceContainerLowest: Colors.white,
          surfaceContainerLow: const Color(0xFFF1F6F2),
          surfaceContainer: const Color(0xFFEAF1EC),
          outline: const Color(0xFFB9C9BE),
          outlineVariant: const Color(0xFFD7E2DA),
        );
    return _base(scheme, lightBackground);
  }

  static ThemeData dark() {
    final scheme =
        ColorScheme.fromSeed(
          seedColor: const Color(0xFF79D5A0),
          brightness: Brightness.dark,
        ).copyWith(
          primary: const Color(0xFF79D5A0),
          onPrimary: const Color(0xFF063920),
          primaryContainer: const Color(0xFF18492F),
          onPrimaryContainer: const Color(0xFFD8F5E2),
          secondary: const Color(0xFFA5DDB8),
          onSecondary: const Color(0xFF12321F),
          secondaryContainer: const Color(0xFF294A35),
          onSecondaryContainer: const Color(0xFFE1F3E6),
          surface: const Color(0xFF17231C),
          onSurface: const Color(0xFFE5EEE8),
          surfaceContainerLowest: const Color(0xFF101813),
          surfaceContainerLow: const Color(0xFF1D2B22),
          surfaceContainer: const Color(0xFF24342A),
          outline: const Color(0xFF718477),
          outlineVariant: const Color(0xFF3C5143),
        );
    return _base(scheme, const Color(0xFF101813));
  }

  static ThemeData _base(ColorScheme scheme, Color background) => ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: background,
    fontFamily: 'Roboto',
    visualDensity: VisualDensity.standard,
    appBarTheme: AppBarTheme(
      backgroundColor: scheme.surface,
      foregroundColor: scheme.onSurface,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      centerTitle: false,
      titleTextStyle: TextStyle(
        color: scheme.onSurface,
        fontSize: 16,
        fontWeight: FontWeight.w700,
      ),
    ),
    cardTheme: CardThemeData(
      color: scheme.surface,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(18),
        side: BorderSide(color: scheme.outlineVariant),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size(48, 48),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(15)),
        textStyle: const TextStyle(fontWeight: FontWeight.w700),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: scheme.surfaceContainerLow,
      hintStyle: TextStyle(color: scheme.onSurfaceVariant),
      contentPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 15),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(20),
        borderSide: BorderSide(color: scheme.outlineVariant),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(20),
        borderSide: BorderSide(color: scheme.outlineVariant),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(20),
        borderSide: BorderSide(color: scheme.primary, width: 1.5),
      ),
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
    ),
    chipTheme: ChipThemeData(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      side: BorderSide(color: scheme.outlineVariant),
    ),
    progressIndicatorTheme: ProgressIndicatorThemeData(color: scheme.primary),
  );
}

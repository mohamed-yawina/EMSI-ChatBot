import 'package:flutter/material.dart';

class AppTheme {
  static const Color navy = Color(0xFF12345A);
  static const Color blue = Color(0xFF2468B4);
  static const Color teal = Color(0xFF2A8C85);

  static ThemeData light() {
    final scheme =
        ColorScheme.fromSeed(
          seedColor: blue,
          brightness: Brightness.light,
          surface: const Color(0xFFFFFFFF),
        ).copyWith(
          primary: navy,
          secondary: teal,
          surface: const Color(0xFFFFFFFF),
          surfaceContainerLowest: const Color(0xFFFFFFFF),
          surfaceContainerLow: const Color(0xFFF7F9FC),
          outline: const Color(0xFFDCE3EC),
        );
    return _base(scheme, const Color(0xFFF3F6FA));
  }

  static ThemeData dark() {
    final scheme =
        ColorScheme.fromSeed(
          seedColor: const Color(0xFF8DB9F1),
          brightness: Brightness.dark,
          surface: const Color(0xFF152338),
        ).copyWith(
          primary: const Color(0xFF9AC4F7),
          secondary: const Color(0xFF6DC5BB),
          surface: const Color(0xFF152338),
          surfaceContainerLowest: const Color(0xFF101C2D),
          surfaceContainerLow: const Color(0xFF1B2A40),
          outline: const Color(0xFF34465E),
        );
    return _base(scheme, const Color(0xFF0E1928));
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
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: scheme.surfaceContainerLow,
      hintStyle: TextStyle(color: scheme.onSurfaceVariant),
      contentPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 15),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(22),
        borderSide: BorderSide(color: scheme.outline),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(22),
        borderSide: BorderSide(color: scheme.outline),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(22),
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
  );
}

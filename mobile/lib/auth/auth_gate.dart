import 'package:flutter/material.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import '../screens/chat_screen.dart';
import '../screens/login_screen.dart';
import '../screens/profile_screen.dart';
import '../screens/set_new_password_screen.dart';
import '../widgets/auth_screen_widgets.dart';
import 'auth_service.dart';

class AuthGate extends StatelessWidget {
  const AuthGate({
    super.key,
    required this.authService,
    required this.themeMode,
    required this.onThemeModeChanged,
    this.supabaseClient,
  });

  final AuthService authService;
  final ThemeMode themeMode;
  final ValueChanged<ThemeMode> onThemeModeChanged;
  final SupabaseClient? supabaseClient;

  @override
  Widget build(BuildContext context) => StreamBuilder<AuthSnapshot>(
    stream: authService.authStateChanges,
    initialData: authService.currentState,
    builder: (context, snapshot) {
      if (snapshot.hasError) {
        return const AuthPageFrame(
          title: 'Session indisponible',
          subtitle: 'La session ne peut pas être vérifiée actuellement. Vérifiez votre connexion puis rechargez l’application.',
          child: AuthStatusMessage(
            message: 'Aucun jeton ni détail technique n’est affiché. Si le problème persiste, reconnectez-vous.',
            success: false,
          ),
        );
      }

      final state = snapshot.data ?? authService.currentState;
      if (state.needsPasswordUpdate) {
        return SetNewPasswordScreen(authService: authService);
      }
      final user = state.user;
      if (user == null) return LoginScreen(authService: authService);

      return ChatScreen(
        themeMode: themeMode,
        onThemeModeChanged: onThemeModeChanged,
        profileEmail: user.email,
        supabaseClient: supabaseClient,
        onProfile: () => Navigator.of(context).push(
          MaterialPageRoute<void>(
            builder: (_) => ProfileScreen(authService: authService),
          ),
        ),
      );
    },
  );
}

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:emsi_chatbot/auth/auth_gate.dart';
import 'package:emsi_chatbot/auth/auth_service.dart';
import 'package:emsi_chatbot/screens/forgot_password_screen.dart';
import 'package:emsi_chatbot/screens/login_screen.dart';
import 'package:emsi_chatbot/screens/profile_screen.dart';
import 'package:emsi_chatbot/screens/register_screen.dart';
import 'package:emsi_chatbot/screens/set_new_password_screen.dart';
import 'package:emsi_chatbot/theme/app_theme.dart';

import 'support/fake_auth_service.dart';

Widget _app(Widget home) => MaterialApp(theme: AppTheme.light(), home: home);

void main() {
  testWidgets('signed-out AuthGate displays the login screen', (tester) async {
    final auth = FakeAuthService();
    addTearDown(auth.dispose);

    await tester.pumpWidget(
      _app(
        AuthGate(
          authService: auth,
          themeMode: ThemeMode.light,
          onThemeModeChanged: (_) {},
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Bon retour'), findsOneWidget);
    expect(find.byKey(const ValueKey('login-submit')), findsOneWidget);
  });

  testWidgets('AuthGate directs a recovery session to password update', (
    tester,
  ) async {
    final auth = FakeAuthService()
      ..setState(
        const AuthSnapshot(
          user: AuthUserInfo(id: 'recovery-user', email: 'person@example.test'),
          needsPasswordUpdate: true,
        ),
      );
    addTearDown(auth.dispose);

    await tester.pumpWidget(
      _app(
        AuthGate(
          authService: auth,
          themeMode: ThemeMode.light,
          onThemeModeChanged: (_) {},
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Choisir un nouveau mot de passe'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('update-password-submit')),
      findsOneWidget,
    );
  });

  testWidgets('login validates fields and submits through AuthService', (
    tester,
  ) async {
    final auth = FakeAuthService();
    addTearDown(auth.dispose);
    await tester.pumpWidget(_app(LoginScreen(authService: auth)));

    await tester.tap(find.byKey(const ValueKey('login-submit')));
    await tester.pumpAndSettle();
    expect(auth.signInCalls, 0);
    expect(find.text('Saisissez votre adresse e-mail.'), findsOneWidget);

    await tester.enterText(
      find.byKey(const ValueKey('login-email')),
      'person@example.test',
    );
    await tester.enterText(
      find.byKey(const ValueKey('login-password')),
      'example-password',
    );
    await tester.tap(find.byKey(const ValueKey('login-submit')));
    await tester.pumpAndSettle();
    expect(auth.signInCalls, 1);
    expect(find.text('Action terminée.'), findsOneWidget);
  });

  testWidgets('register validates and shows the confirmation result', (
    tester,
  ) async {
    final auth = FakeAuthService()
      ..nextResult = const AuthActionResult(
        succeeded: true,
        message: 'Vérifiez votre e-mail pour confirmer votre compte.',
      );
    addTearDown(auth.dispose);
    await tester.pumpWidget(_app(RegisterScreen(authService: auth)));

    await tester.enterText(
      find.byKey(const ValueKey('register-email')),
      'person@example.test',
    );
    await tester.enterText(
      find.byKey(const ValueKey('register-password')),
      'safe-password',
    );
    await tester.enterText(
      find.byKey(const ValueKey('register-confirm-password')),
      'safe-password',
    );
    await tester.ensureVisible(find.byKey(const ValueKey('register-submit')));
    await tester.tap(find.byKey(const ValueKey('register-submit')));
    await tester.pumpAndSettle();

    expect(auth.registerCalls, 1);
    expect(
      find.text('Vérifiez votre e-mail pour confirmer votre compte.'),
      findsOneWidget,
    );
  });

  testWidgets('password reset request shows the generic result', (
    tester,
  ) async {
    final auth = FakeAuthService()
      ..nextResult = const AuthActionResult(
        succeeded: true,
        message:
            'Si cette adresse correspond à un compte, un lien sera envoyé.',
      );
    addTearDown(auth.dispose);
    await tester.pumpWidget(_app(ForgotPasswordScreen(authService: auth)));

    await tester.enterText(
      find.byKey(const ValueKey('reset-email')),
      'person@example.test',
    );
    await tester.tap(find.byKey(const ValueKey('reset-submit')));
    await tester.pumpAndSettle();
    expect(auth.resetCalls, 1);
    expect(find.textContaining('Si cette adresse correspond'), findsOneWidget);
  });

  testWidgets('password update validates and calls recovery action', (
    tester,
  ) async {
    final auth = FakeAuthService();
    addTearDown(auth.dispose);
    await tester.pumpWidget(_app(SetNewPasswordScreen(authService: auth)));

    await tester.enterText(
      find.byKey(const ValueKey('new-password')),
      'a-secure-password',
    );
    await tester.enterText(
      find.byKey(const ValueKey('confirm-new-password')),
      'a-secure-password',
    );
    await tester.tap(find.byKey(const ValueKey('update-password-submit')));
    await tester.pumpAndSettle();
    expect(find.text('Action terminée.'), findsOneWidget);
  });

  testWidgets('profile shows the actual email and signs out', (tester) async {
    final auth = FakeAuthService(
      user: const AuthUserInfo(
        id: 'profile-user',
        email: 'person@example.test',
      ),
    );
    addTearDown(auth.dispose);
    await tester.pumpWidget(
      _app(
        Builder(
          builder: (context) => Scaffold(
            body: TextButton(
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => ProfileScreen(authService: auth),
                ),
              ),
              child: const Text('Open profile'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('Open profile'));
    await tester.pumpAndSettle();
    expect(find.text('person@example.test'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('profile-signout')));
    await tester.pumpAndSettle();
    expect(auth.signOutCalls, 1);
    expect(find.text('Open profile'), findsOneWidget);
  });
}

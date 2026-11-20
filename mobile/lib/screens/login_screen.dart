import 'package:flutter/material.dart';

import '../auth/auth_service.dart';
import '../widgets/auth_screen_widgets.dart';
import 'forgot_password_screen.dart';
import 'register_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key, required this.authService});

  final AuthService authService;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _loading = false;
  bool _obscurePassword = true;
  AuthActionResult? _result;

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _signIn() async {
    if (_loading || !_formKey.currentState!.validate()) return;
    setState(() {
      _loading = true;
      _result = null;
    });
    final result = await widget.authService.signIn(
      email: _emailController.text.trim(),
      password: _passwordController.text,
    );
    if (!mounted) return;
    setState(() {
      _loading = false;
      _result = result;
    });
  }

  @override
  Widget build(BuildContext context) => AuthPageFrame(
    title: 'Bon retour',
    subtitle: 'Connectez-vous pour accéder à EMSI-ChatBot.',
    child: Form(
      key: _formKey,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          TextFormField(
            key: const ValueKey('login-email'),
            controller: _emailController,
            keyboardType: TextInputType.emailAddress,
            autofillHints: const [AutofillHints.username, AutofillHints.email],
            textInputAction: TextInputAction.next,
            decoration: const InputDecoration(
              labelText: 'Adresse e-mail',
              prefixIcon: Icon(Icons.mail_outline_rounded),
            ),
            validator: _validateEmail,
          ),
          const SizedBox(height: 14),
          TextFormField(
            key: const ValueKey('login-password'),
            controller: _passwordController,
            obscureText: _obscurePassword,
            autofillHints: const [AutofillHints.password],
            textInputAction: TextInputAction.done,
            onFieldSubmitted: (_) => _signIn(),
            decoration: InputDecoration(
              labelText: 'Mot de passe',
              prefixIcon: const Icon(Icons.lock_outline_rounded),
              suffixIcon: IconButton(
                tooltip: _obscurePassword
                    ? 'Afficher le mot de passe'
                    : 'Masquer le mot de passe',
                onPressed: () =>
                    setState(() => _obscurePassword = !_obscurePassword),
                icon: Icon(
                  _obscurePassword
                      ? Icons.visibility_outlined
                      : Icons.visibility_off_outlined,
                ),
              ),
            ),
            validator: (value) => value == null || value.isEmpty
                ? 'Saisissez votre mot de passe.'
                : null,
          ),
          Align(
            alignment: Alignment.centerRight,
            child: TextButton(
              onPressed: _loading
                  ? null
                  : () => Navigator.of(context).push(
                      MaterialPageRoute<void>(
                        builder: (_) => ForgotPasswordScreen(
                          authService: widget.authService,
                          initialEmail: _emailController.text.trim(),
                        ),
                      ),
                    ),
              child: const Text('Mot de passe oublié ?'),
            ),
          ),
          if (_result != null) ...[
            AuthStatusMessage(
              message: _result!.message,
              success: _result!.succeeded,
            ),
            const SizedBox(height: 14),
          ],
          FilledButton.icon(
            key: const ValueKey('login-submit'),
            onPressed: _loading ? null : _signIn,
            icon: _loading
                ? const SizedBox.square(
                    dimension: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.login_rounded),
            label: Text(_loading ? 'Connexion…' : 'Se connecter'),
          ),
          const SizedBox(height: 12),
          OutlinedButton(
            onPressed: _loading
                ? null
                : () => Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (_) =>
                          RegisterScreen(authService: widget.authService),
                    ),
                  ),
            child: const Text('Créer un compte'),
          ),
        ],
      ),
    ),
  );
}

String? _validateEmail(String? value) {
  final email = value?.trim() ?? '';
  if (email.isEmpty) return 'Saisissez votre adresse e-mail.';
  if (!RegExp(r'^[^\s@]+@[^\s@]+\.[^\s@]+$').hasMatch(email)) {
    return 'Saisissez une adresse e-mail valide.';
  }
  return null;
}

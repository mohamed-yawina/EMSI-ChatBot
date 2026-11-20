import 'package:flutter/material.dart';

import '../auth/auth_service.dart';
import '../widgets/auth_screen_widgets.dart';

class RegisterScreen extends StatefulWidget {
  const RegisterScreen({super.key, required this.authService});

  final AuthService authService;

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  final _formKey = GlobalKey<FormState>();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  final _confirmController = TextEditingController();
  bool _loading = false;
  AuthActionResult? _result;

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    _confirmController.dispose();
    super.dispose();
  }

  Future<void> _register() async {
    if (_loading || !_formKey.currentState!.validate()) return;
    setState(() {
      _loading = true;
      _result = null;
    });
    final result = await widget.authService.register(
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
    title: 'Créer votre compte',
    subtitle: 'Un lien de confirmation sera envoyé à votre adresse e-mail.',
    showBackButton: true,
    child: Form(
      key: _formKey,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          TextFormField(
            key: const ValueKey('register-email'),
            controller: _emailController,
            keyboardType: TextInputType.emailAddress,
            autofillHints: const [AutofillHints.email],
            textInputAction: TextInputAction.next,
            decoration: const InputDecoration(
              labelText: 'Adresse e-mail',
              prefixIcon: Icon(Icons.mail_outline_rounded),
            ),
            validator: _validateEmail,
          ),
          const SizedBox(height: 14),
          TextFormField(
            key: const ValueKey('register-password'),
            controller: _passwordController,
            obscureText: true,
            autofillHints: const [AutofillHints.newPassword],
            textInputAction: TextInputAction.next,
            decoration: const InputDecoration(
              labelText: 'Mot de passe',
              helperText: '8 caractères minimum.',
              prefixIcon: Icon(Icons.lock_outline_rounded),
            ),
            validator: (value) => (value?.length ?? 0) < 8
                ? 'Utilisez au moins 8 caractères.'
                : null,
          ),
          const SizedBox(height: 14),
          TextFormField(
            key: const ValueKey('register-confirm-password'),
            controller: _confirmController,
            obscureText: true,
            textInputAction: TextInputAction.done,
            onFieldSubmitted: (_) => _register(),
            decoration: const InputDecoration(
              labelText: 'Confirmer le mot de passe',
              prefixIcon: Icon(Icons.lock_reset_rounded),
            ),
            validator: (value) => value != _passwordController.text
                ? 'Les mots de passe ne correspondent pas.'
                : null,
          ),
          if (_result != null) ...[
            const SizedBox(height: 14),
            AuthStatusMessage(
              message: _result!.message,
              success: _result!.succeeded,
            ),
          ],
          const SizedBox(height: 18),
          FilledButton.icon(
            key: const ValueKey('register-submit'),
            onPressed: _loading ? null : _register,
            icon: _loading
                ? const SizedBox.square(
                    dimension: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.person_add_alt_1_rounded),
            label: Text(_loading ? 'Création…' : 'Créer le compte'),
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

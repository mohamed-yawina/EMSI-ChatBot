import 'package:flutter/material.dart';

import '../auth/auth_service.dart';
import '../widgets/auth_screen_widgets.dart';

class ForgotPasswordScreen extends StatefulWidget {
  const ForgotPasswordScreen({
    super.key,
    required this.authService,
    this.initialEmail = '',
  });

  final AuthService authService;
  final String initialEmail;

  @override
  State<ForgotPasswordScreen> createState() => _ForgotPasswordScreenState();
}

class _ForgotPasswordScreenState extends State<ForgotPasswordScreen> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _emailController = TextEditingController(
    text: widget.initialEmail,
  );
  bool _loading = false;
  AuthActionResult? _result;

  @override
  void dispose() {
    _emailController.dispose();
    super.dispose();
  }

  Future<void> _sendResetLink() async {
    if (_loading || !_formKey.currentState!.validate()) return;
    setState(() {
      _loading = true;
      _result = null;
    });
    final result = await widget.authService.requestPasswordReset(
      email: _emailController.text.trim(),
    );
    if (!mounted) return;
    setState(() {
      _loading = false;
      _result = result;
    });
  }

  @override
  Widget build(BuildContext context) => AuthPageFrame(
    title: 'Réinitialiser le mot de passe',
    subtitle:
        'Nous vous enverrons un lien pour choisir un nouveau mot de passe.',
    showBackButton: true,
    child: Form(
      key: _formKey,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          TextFormField(
            key: const ValueKey('reset-email'),
            controller: _emailController,
            keyboardType: TextInputType.emailAddress,
            autofillHints: const [AutofillHints.email],
            textInputAction: TextInputAction.done,
            onFieldSubmitted: (_) => _sendResetLink(),
            decoration: const InputDecoration(
              labelText: 'Adresse e-mail',
              prefixIcon: Icon(Icons.mail_outline_rounded),
            ),
            validator: _validateEmail,
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
            key: const ValueKey('reset-submit'),
            onPressed: _loading ? null : _sendResetLink,
            icon: _loading
                ? const SizedBox.square(
                    dimension: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.mark_email_read_outlined),
            label: Text(_loading ? 'Envoi…' : 'Envoyer le lien'),
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

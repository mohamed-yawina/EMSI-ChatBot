import 'package:flutter/material.dart';

import '../auth/auth_service.dart';
import '../widgets/auth_screen_widgets.dart';

class SetNewPasswordScreen extends StatefulWidget {
  const SetNewPasswordScreen({super.key, required this.authService});

  final AuthService authService;

  @override
  State<SetNewPasswordScreen> createState() => _SetNewPasswordScreenState();
}

class _SetNewPasswordScreenState extends State<SetNewPasswordScreen> {
  final _formKey = GlobalKey<FormState>();
  final _passwordController = TextEditingController();
  final _confirmController = TextEditingController();
  bool _loading = false;
  AuthActionResult? _result;

  @override
  void dispose() {
    _passwordController.dispose();
    _confirmController.dispose();
    super.dispose();
  }

  Future<void> _updatePassword() async {
    if (_loading || !_formKey.currentState!.validate()) return;
    setState(() {
      _loading = true;
      _result = null;
    });
    final result = await widget.authService.updateRecoveryPassword(
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
    title: 'Choisir un nouveau mot de passe',
    subtitle: 'Utilisez au moins 8 caractères.',
    child: Form(
      key: _formKey,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          TextFormField(
            key: const ValueKey('new-password'),
            controller: _passwordController,
            obscureText: true,
            autofillHints: const [AutofillHints.newPassword],
            textInputAction: TextInputAction.next,
            decoration: const InputDecoration(
              labelText: 'Nouveau mot de passe',
              prefixIcon: Icon(Icons.lock_outline_rounded),
            ),
            validator: (value) => (value?.length ?? 0) < 8
                ? 'Utilisez au moins 8 caractères.'
                : null,
          ),
          const SizedBox(height: 14),
          TextFormField(
            key: const ValueKey('confirm-new-password'),
            controller: _confirmController,
            obscureText: true,
            textInputAction: TextInputAction.done,
            onFieldSubmitted: (_) => _updatePassword(),
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
            key: const ValueKey('update-password-submit'),
            onPressed: _loading ? null : _updatePassword,
            icon: _loading
                ? const SizedBox.square(
                    dimension: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.password_rounded),
            label: Text(_loading ? 'Mise à jour…' : 'Mettre à jour'),
          ),
        ],
      ),
    ),
  );
}

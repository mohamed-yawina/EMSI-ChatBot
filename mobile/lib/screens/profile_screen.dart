import 'package:flutter/material.dart';

import '../auth/auth_service.dart';
import '../widgets/auth_screen_widgets.dart';

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key, required this.authService});

  final AuthService authService;

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  bool _loading = false;
  AuthActionResult? _result;

  Future<void> _signOut() async {
    if (_loading) return;
    setState(() {
      _loading = true;
      _result = null;
    });
    final result = await widget.authService.signOut();
    if (!mounted) return;
    setState(() {
      _loading = false;
      _result = result;
    });
    if (result.succeeded && mounted) Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    final user = widget.authService.currentState.user;
    return Scaffold(
      appBar: AppBar(title: const Text('Profil')),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 560),
          child: ListView(
            padding: const EdgeInsets.all(20),
            shrinkWrap: true,
            children: [
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(22),
                  child: Column(
                    children: [
                      CircleAvatar(
                        radius: 34,
                        backgroundColor: Theme.of(context)
                            .colorScheme
                            .primaryContainer,
                        child: Icon(
                          Icons.person_outline_rounded,
                          color: Theme.of(context).colorScheme.primary,
                          size: 34,
                        ),
                      ),
                      const SizedBox(height: 16),
                      Text(
                        user?.email ?? 'Utilisateur connecté',
                        textAlign: TextAlign.center,
                        style: Theme.of(context).textTheme.titleMedium
                            ?.copyWith(fontWeight: FontWeight.w700),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        'Compte géré par Supabase Auth',
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: Theme.of(context).colorScheme.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              if (_result != null) ...[
                const SizedBox(height: 14),
                AuthStatusMessage(
                  message: _result!.message,
                  success: _result!.succeeded,
                ),
              ],
              const SizedBox(height: 16),
              OutlinedButton.icon(
                key: const ValueKey('profile-signout'),
                onPressed: _loading ? null : _signOut,
                icon: _loading
                    ? const SizedBox.square(
                        dimension: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.logout_rounded),
                label: Text(_loading ? 'Déconnexion…' : 'Se déconnecter'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

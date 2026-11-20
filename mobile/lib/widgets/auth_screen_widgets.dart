import 'package:flutter/material.dart';

class AuthPageFrame extends StatelessWidget {
  const AuthPageFrame({
    super.key,
    required this.title,
    required this.subtitle,
    required this.child,
    this.showBackButton = false,
  });

  final String title;
  final String subtitle;
  final Widget child;
  final bool showBackButton;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: showBackButton
          ? AppBar(
              leading: BackButton(onPressed: () => Navigator.maybePop(context)),
              backgroundColor: Colors.transparent,
            )
          : null,
      body: DecoratedBox(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              Theme.of(context).scaffoldBackgroundColor,
              colors.primaryContainer.withValues(alpha: 0.55),
            ],
          ),
        ),
        child: SafeArea(
          top: !showBackButton,
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(20, 24, 20, 32),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 440),
                child: Card(
                  child: Padding(
                    padding: const EdgeInsets.all(26),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Center(
                          child: Container(
                            width: 54,
                            height: 54,
                            decoration: BoxDecoration(
                              color: colors.primary,
                              borderRadius: BorderRadius.circular(18),
                              boxShadow: [
                                BoxShadow(
                                  color: colors.primary.withValues(alpha: 0.18),
                                  blurRadius: 16,
                                  offset: const Offset(0, 7),
                                ),
                              ],
                            ),
                            child: Icon(
                              Icons.school_rounded,
                              color: colors.onPrimary,
                              size: 28,
                            ),
                          ),
                        ),
                        const SizedBox(height: 18),
                        Text(
                          'EMSI-ChatBot',
                          textAlign: TextAlign.center,
                          style: Theme.of(context).textTheme.titleMedium
                              ?.copyWith(
                                color: colors.primary,
                                fontWeight: FontWeight.w800,
                                letterSpacing: 0.2,
                              ),
                        ),
                        const SizedBox(height: 22),
                        Text(
                          title,
                          textAlign: TextAlign.center,
                          style: Theme.of(context).textTheme.headlineSmall
                              ?.copyWith(fontWeight: FontWeight.w800),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          subtitle,
                          textAlign: TextAlign.center,
                          style: Theme.of(context).textTheme.bodyMedium
                              ?.copyWith(
                                color: colors.onSurfaceVariant,
                                height: 1.5,
                              ),
                        ),
                        const SizedBox(height: 24),
                        child,
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class AuthStatusMessage extends StatelessWidget {
  const AuthStatusMessage({
    super.key,
    required this.message,
    required this.success,
  });

  final String message;
  final bool success;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final background = success
        ? colors.primaryContainer
        : colors.errorContainer;
    final foreground = success
        ? colors.onPrimaryContainer
        : colors.onErrorContainer;
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            success ? Icons.check_circle_outline : Icons.error_outline,
            color: foreground,
            size: 19,
          ),
          const SizedBox(width: 9),
          Expanded(
            child: Text(
              message,
              style: Theme.of(context).textTheme.bodySmall
                  ?.copyWith(color: foreground, height: 1.45),
            ),
          ),
        ],
      ),
    );
  }
}

class AuthConfigMissingPage extends StatelessWidget {
  const AuthConfigMissingPage({super.key});

  @override
  Widget build(BuildContext context) => AuthPageFrame(
    title: 'Configuration Supabase requise',
    subtitle: 'Ajoutez SUPABASE_URL et SUPABASE_PUBLISHABLE_KEY à la configuration de compilation Flutter, puis relancez l’application.',
    child: const AuthStatusMessage(
      message: 'Aucun compte de démonstration n’est créé. Les connexions restent désactivées tant que les identifiants du projet ne sont pas configurés.',
      success: false,
    ),
  );
}

class AuthInitializationErrorPage extends StatelessWidget {
  const AuthInitializationErrorPage({super.key});

  @override
  Widget build(BuildContext context) => AuthPageFrame(
    title: 'Connexion au service indisponible',
    subtitle: 'Supabase n’a pas pu être initialisé. Vérifiez votre connexion et la configuration du projet, puis rechargez l’application.',
    child: const AuthStatusMessage(
      message: 'Aucun jeton ni détail technique n’est affiché. Si le problème persiste, vérifiez les paramètres de redirection et réessayez.',
      success: false,
    ),
  );
}

import 'package:flutter/material.dart';

class AppSidebar extends StatelessWidget {
  const AppSidebar({
    super.key,
    required this.isDarkMode,
    required this.onNewConversation,
    required this.onThemeChanged,
    required this.onSettings,
    this.onClose,
  });

  final bool isDarkMode;
  final VoidCallback onNewConversation;
  final ValueChanged<bool> onThemeChanged;
  final VoidCallback onSettings;
  final VoidCallback? onClose;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;
    return Container(
      width: 280,
      decoration: BoxDecoration(
        color: colors.surfaceContainerLow,
        border: Border(right: BorderSide(color: colors.outlineVariant)),
      ),
      child: Material(
        color: colors.surfaceContainerLow,
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(18, 20, 18, 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(
                  children: [
                    Container(
                      width: 42,
                      height: 42,
                      decoration: BoxDecoration(
                        color: colors.primary,
                        borderRadius: BorderRadius.circular(14),
                      ),
                      child: Icon(
                        Icons.school_rounded,
                        color: colors.onPrimary,
                      ),
                    ),
                    const SizedBox(width: 11),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'EMSI',
                            style: theme.textTheme.titleMedium?.copyWith(
                              fontWeight: FontWeight.w800,
                              letterSpacing: 0.6,
                            ),
                          ),
                          Text(
                            'ASSISTANT DOCUMENTAIRE',
                            style: theme.textTheme.labelSmall?.copyWith(
                              color: colors.onSurfaceVariant,
                              letterSpacing: 0.7,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 28),
                FilledButton.icon(
                  onPressed: () {
                    onNewConversation();
                    onClose?.call();
                  },
                  icon: const Icon(Icons.add_rounded),
                  label: const Text('Nouvelle conversation'),
                  style: FilledButton.styleFrom(
                    minimumSize: const Size.fromHeight(48),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(14),
                    ),
                  ),
                ),
                const SizedBox(height: 24),
                Text(
                  'VOTRE ASSISTANT',
                  style: theme.textTheme.labelSmall?.copyWith(
                    color: colors.onSurfaceVariant,
                    letterSpacing: 1,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 9),
                Text(
                  'Explorez la brochure EMSI grâce à la recherche documentaire et aux réponses sourcées.',
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: colors.onSurfaceVariant,
                    height: 1.5,
                  ),
                ),
                const SizedBox(height: 17),
                Wrap(
                  spacing: 7,
                  runSpacing: 7,
                  children: const [
                    _TechTag(label: 'RAG'),
                    _TechTag(label: 'Brochure EMSI'),
                    _TechTag(label: 'Images facultatives'),
                  ],
                ),
                const Spacer(),
                const Divider(),
                SwitchListTile.adaptive(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Mode sombre'),
                  secondary: Icon(
                    isDarkMode ? Icons.dark_mode : Icons.light_mode,
                  ),
                  value: isDarkMode,
                  onChanged: onThemeChanged,
                ),
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.tune_rounded),
                  title: const Text('Paramètres'),
                  trailing: const Icon(Icons.chevron_right_rounded),
                  onTap: () {
                    onSettings();
                    onClose?.call();
                  },
                ),
                const SizedBox(height: 6),
                Text(
                  'Les conversations ne sont pas enregistrées côté serveur.',
                  style: theme.textTheme.labelSmall?.copyWith(
                    color: colors.onSurfaceVariant,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _TechTag extends StatelessWidget {
  const _TechTag({required this.label});
  final String label;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 6),
      decoration: BoxDecoration(
        color: colors.surface,
        border: Border.all(color: colors.outlineVariant),
        borderRadius: BorderRadius.circular(9),
      ),
      child: Text(label, style: Theme.of(context).textTheme.labelSmall),
    );
  }
}

class WelcomePanel extends StatelessWidget {
  const WelcomePanel({super.key, required this.onSuggestion});

  final ValueChanged<String> onSuggestion;

  static const suggestions = [
    'Quels sont les campus EMSI ?',
    'Quelles sont les filières proposées ?',
    'Comment fonctionne la formation à l’EMSI ?',
    'Quelles informations contient la brochure ?',
  ];

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 760),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 56,
                height: 56,
                decoration: BoxDecoration(
                  color: colors.primaryContainer,
                  borderRadius: BorderRadius.circular(18),
                ),
                child: Icon(
                  Icons.auto_awesome_rounded,
                  color: colors.primary,
                  size: 27,
                ),
              ),
              const SizedBox(height: 22),
              Text(
                'Bonjour, que souhaitez-vous découvrir ?',
                style: theme.textTheme.headlineSmall?.copyWith(
                  fontWeight: FontWeight.w700,
                  height: 1.2,
                ),
              ),
              const SizedBox(height: 10),
              Text(
                'Posez une question sur les campus, les formations ou les informations de la brochure EMSI.',
                style: theme.textTheme.bodyLarge?.copyWith(
                  color: colors.onSurfaceVariant,
                  height: 1.55,
                ),
              ),
              const SizedBox(height: 26),
              Text(
                'Pour commencer',
                style: theme.textTheme.titleSmall?.copyWith(
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 12),
              LayoutBuilder(
                builder: (context, constraints) {
                  final columns = constraints.maxWidth < 540 ? 1 : 2;
                  final width =
                      (constraints.maxWidth - (columns - 1) * 10) / columns;
                  return Wrap(
                    spacing: 10,
                    runSpacing: 10,
                    children: [
                      for (var index = 0; index < suggestions.length; index++)
                        SizedBox(
                          width: width,
                          child: _SuggestionCard(
                            text: suggestions[index],
                            icon: [
                              Icons.location_city_rounded,
                              Icons.school_outlined,
                              Icons.menu_book_rounded,
                              Icons.description_outlined,
                            ][index],
                            onTap: () => onSuggestion(suggestions[index]),
                          ),
                        ),
                    ],
                  );
                },
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SuggestionCard extends StatelessWidget {
  const _SuggestionCard({
    required this.text,
    required this.icon,
    required this.onTap,
  });

  final String text;
  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Card(
      elevation: 0,
      color: colors.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: colors.outlineVariant),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(15),
          child: Row(
            children: [
              Icon(icon, color: colors.secondary, size: 20),
              const SizedBox(width: 11),
              Expanded(
                child: Text(
                  text,
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
              ),
              Icon(
                Icons.arrow_outward_rounded,
                color: colors.onSurfaceVariant,
                size: 17,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class ChatComposer extends StatelessWidget {
  const ChatComposer({
    super.key,
    required this.controller,
    required this.isLoading,
    required this.includeImages,
    required this.onIncludeImagesChanged,
    required this.onSend,
  });

  final TextEditingController controller;
  final bool isLoading;
  final bool includeImages;
  final ValueChanged<bool> onIncludeImagesChanged;
  final VoidCallback onSend;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Material(
      color: theme.colorScheme.surface,
      child: SafeArea(
        top: false,
        child: Container(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
          decoration: BoxDecoration(
            border: Border(
              top: BorderSide(color: theme.colorScheme.outlineVariant),
            ),
          ),
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 920),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Expanded(
                        child: TextField(
                          controller: controller,
                          enabled: !isLoading,
                          minLines: 1,
                          maxLines: 5,
                          textCapitalization: TextCapitalization.sentences,
                          textInputAction: TextInputAction.send,
                          onSubmitted: (_) => onSend(),
                          decoration: InputDecoration(
                            hintText: "Posez votre question sur l'EMSI...",
                            prefixIcon: const Icon(
                              Icons.chat_bubble_outline_rounded,
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Tooltip(
                        message: 'Envoyer',
                        child: SizedBox(
                          height: 52,
                          width: 54,
                          child: FilledButton(
                            onPressed: isLoading ? null : onSend,
                            style: FilledButton.styleFrom(
                              padding: EdgeInsets.zero,
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(16),
                              ),
                            ),
                            child: isLoading
                                ? const SizedBox(
                                    width: 19,
                                    height: 19,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                    ),
                                  )
                                : const Icon(Icons.arrow_upward_rounded),
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 7),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: Tooltip(
                      message: 'Active la recherche facultative d’images dans la brochure.',
                      child: FilterChip(
                        avatar: Icon(
                          includeImages
                              ? Icons.image_rounded
                              : Icons.image_outlined,
                          size: 17,
                        ),
                        label: const Text('Recherche d’images'),
                        selected: includeImages,
                        onSelected: isLoading ? null : onIncludeImagesChanged,
                        visualDensity: VisualDensity.compact,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

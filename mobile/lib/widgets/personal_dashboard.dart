import 'package:flutter/material.dart';

import '../models/conversation_models.dart';

class PersonalDashboard extends StatelessWidget {
  const PersonalDashboard({
    super.key,
    required this.email,
    required this.stats,
    required this.recentConversations,
    required this.isLoading,
    this.errorMessage,
    required this.onNewConversation,
    required this.onOpenConversation,
    required this.onHistory,
    required this.onRetry,
  });

  final String? email;
  final DashboardStats? stats;
  final List<ConversationSummary> recentConversations;
  final bool isLoading;
  final String? errorMessage;
  final VoidCallback onNewConversation;
  final ValueChanged<ConversationSummary> onOpenConversation;
  final VoidCallback onHistory;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 960),
        child: ListView(
          padding: const EdgeInsets.fromLTRB(24, 30, 24, 36),
          children: [
            Text('Bonjour,', style: theme.textTheme.titleMedium),
            const SizedBox(height: 3),
            Text(
              key: const ValueKey('dashboard-user-email'),
              email ?? 'votre espace EMSI',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: theme.textTheme.headlineSmall?.copyWith(
                color: colors.primary,
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'Reprenez une conversation ou interrogez la brochure EMSI.',
              style: theme.textTheme.bodyLarge?.copyWith(
                color: colors.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 22),
            Align(
              alignment: Alignment.centerLeft,
              child: FilledButton.icon(
                key: const ValueKey('dashboard-new-conversation'),
                onPressed: isLoading ? null : onNewConversation,
                icon: const Icon(Icons.add_rounded),
                label: const Text('Nouvelle conversation'),
              ),
            ),
            const SizedBox(height: 26),
            if (isLoading && stats == null)
              const Center(child: CircularProgressIndicator())
            else if (errorMessage != null && stats == null)
              Card(
                child: ListTile(
                  leading: Icon(Icons.cloud_off_outlined, color: colors.error),
                  title: Text(errorMessage!),
                  trailing: TextButton(
                    onPressed: onRetry,
                    child: const Text('Réessayer'),
                  ),
                ),
              )
            else if (stats != null)
              LayoutBuilder(
                builder: (context, constraints) {
                  final count = constraints.maxWidth < 560 ? 2 : 4;
                  final gap = 10.0;
                  final width =
                      (constraints.maxWidth - gap * (count - 1)) / count;
                  final items = [
                    (
                      'Conversations',
                      stats!.conversationCount,
                      Icons.forum_outlined,
                    ),
                    ('Messages', stats!.messageCount, Icons.chat_outlined),
                    (
                      'Favoris',
                      stats!.favoriteCount,
                      Icons.star_outline_rounded,
                    ),
                    (
                      'Dernière activité',
                      stats!.lastActivity == null
                          ? '—'
                          : _formatDate(stats!.lastActivity!),
                      Icons.schedule_rounded,
                    ),
                  ];
                  return Wrap(
                    spacing: gap,
                    runSpacing: gap,
                    children: [
                      for (final item in items)
                        SizedBox(
                          width: width,
                          child: Card(
                            child: Padding(
                              padding: const EdgeInsets.all(15),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Icon(item.$3, color: colors.primary),
                                  const SizedBox(height: 12),
                                  Text(
                                    '${item.$2}',
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: theme.textTheme.titleLarge?.copyWith(
                                      fontWeight: FontWeight.w800,
                                    ),
                                  ),
                                  Text(
                                    item.$1,
                                    style: theme.textTheme.labelMedium
                                        ?.copyWith(
                                          color: colors.onSurfaceVariant,
                                        ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ),
                    ],
                  );
                },
              ),
            const SizedBox(height: 28),
            LayoutBuilder(
              builder: (context, constraints) {
                final title = Text(
                  'Conversations récentes',
                  style: theme.textTheme.titleLarge?.copyWith(
                    fontWeight: FontWeight.w800,
                  ),
                );
                final historyButton = TextButton.icon(
                  onPressed: onHistory,
                  icon: const Icon(Icons.history_rounded),
                  label: const Text('Historique dans la barre latérale'),
                );
                if (constraints.maxWidth < 540) {
                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [title, historyButton],
                  );
                }
                return Row(
                  children: [
                    Expanded(child: title),
                    historyButton,
                  ],
                );
              },
            ),
            const SizedBox(height: 10),
            if (recentConversations.isEmpty && !isLoading)
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Text(
                    'Vos conversations enregistrées apparaîtront ici.',
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: colors.onSurfaceVariant,
                    ),
                  ),
                ),
              )
            else
              for (final conversation in recentConversations.take(5))
                Card(
                  clipBehavior: Clip.antiAlias,
                  child: ListTile(
                    key: ValueKey('dashboard-conversation-${conversation.id}'),
                    leading: Icon(
                      conversation.isFavorite
                          ? Icons.star_rounded
                          : Icons.chat_bubble_outline_rounded,
                      color: conversation.isFavorite
                          ? colors.tertiary
                          : colors.primary,
                    ),
                    title: Text(
                      conversation.title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    subtitle: Text(
                      conversation.lastMessage ?? 'Aucun message',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    trailing: Text(_formatDate(conversation.updatedAt)),
                    onTap: () => onOpenConversation(conversation),
                  ),
                ),
          ],
        ),
      ),
    );
  }

  String _formatDate(DateTime date) {
    final local = date.toLocal();
    final now = DateTime.now();
    if (local.year == now.year &&
        local.month == now.month &&
        local.day == now.day) {
      return '${local.hour.toString().padLeft(2, '0')}:${local.minute.toString().padLeft(2, '0')}';
    }
    return '${local.day.toString().padLeft(2, '0')}/${local.month.toString().padLeft(2, '0')}/${local.year}';
  }
}

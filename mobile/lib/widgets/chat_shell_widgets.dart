import 'package:flutter/material.dart';

import '../models/conversation_models.dart';
import '../services/image_selection_service.dart';

class AppSidebar extends StatelessWidget {
  const AppSidebar({
    super.key,
    required this.isDarkMode,
    required this.onNewConversation,
    required this.onThemeChanged,
    required this.onSettings,
    this.onClose,
    this.isCompact = false,
    this.profileEmail,
    this.onProfile,
    this.conversations = const [],
    this.activeConversationId,
    this.searchQuery = '',
    this.searchController,
    this.showArchived = false,
    this.favoritesOnly = false,
    this.isLoadingConversations = false,
    this.hasMoreConversations = false,
    this.onDashboard,
    this.onHistory,
    this.onFavorites,
    this.onSearchChanged,
    this.onArchivedChanged,
    this.onOpenConversation,
    this.onRenameConversation,
    this.onDeleteConversation,
    this.onArchiveConversation,
    this.onFavoriteConversation,
    this.onLoadMore,
  });

  final bool isDarkMode;
  final VoidCallback onNewConversation;
  final ValueChanged<bool> onThemeChanged;
  final VoidCallback onSettings;
  final VoidCallback? onClose;
  final bool isCompact;
  final String? profileEmail;
  final VoidCallback? onProfile;
  final List<ConversationSummary> conversations;
  final String? activeConversationId;
  final String searchQuery;
  final TextEditingController? searchController;
  final bool showArchived;
  final bool favoritesOnly;
  final bool isLoadingConversations;
  final bool hasMoreConversations;
  final VoidCallback? onDashboard;
  final VoidCallback? onHistory;
  final VoidCallback? onFavorites;
  final ValueChanged<String>? onSearchChanged;
  final ValueChanged<bool>? onArchivedChanged;
  final ValueChanged<ConversationSummary>? onOpenConversation;
  final ValueChanged<ConversationSummary>? onRenameConversation;
  final ValueChanged<ConversationSummary>? onDeleteConversation;
  final ValueChanged<ConversationSummary>? onArchiveConversation;
  final ValueChanged<ConversationSummary>? onFavoriteConversation;
  final VoidCallback? onLoadMore;

  void _closeIfNeeded() => onClose?.call();

  void _closeAndDashboard() {
    onDashboard?.call();
    _closeIfNeeded();
  }

  void _closeAndHistory() {
    onHistory?.call();
    _closeIfNeeded();
  }

  void _closeAndFavorites() {
    onFavorites?.call();
    _closeIfNeeded();
  }

  Widget _buildConversationList() {
    if (isLoadingConversations && conversations.isEmpty) {
      return const Center(child: CircularProgressIndicator(strokeWidth: 2));
    }
    if (conversations.isEmpty) {
      return Center(
        child: Text(
          searchQuery.trim().isNotEmpty
              ? 'Aucun résultat pour cette recherche.'
              : showArchived
              ? 'Aucune conversation archivée'
              : 'Aucune conversation',
          textAlign: TextAlign.center,
        ),
      );
    }
    return ListView.builder(
      itemCount: conversations.length + (hasMoreConversations ? 1 : 0),
      itemBuilder: (context, index) {
        if (index == conversations.length) {
          return TextButton(
            onPressed: onLoadMore,
            child: const Text('Charger plus'),
          );
        }
        final conversation = conversations[index];
        return _ConversationEntry(
          conversation: conversation,
          selected: conversation.id == activeConversationId,
          onTap: onOpenConversation == null
              ? null
              : () {
                  onOpenConversation!(conversation);
                  _closeIfNeeded();
                },
          onRename: onRenameConversation == null
              ? null
              : () => onRenameConversation!(conversation),
          onDelete: onDeleteConversation == null
              ? null
              : () => onDeleteConversation!(conversation),
          onArchive: onArchiveConversation == null
              ? null
              : () => onArchiveConversation!(conversation),
          onFavorite: onFavoriteConversation == null
              ? null
              : () => onFavoriteConversation!(conversation),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;
    return Container(
      width: isCompact ? 76 : 278,
      decoration: BoxDecoration(
        color: colors.surface,
        border: Border(right: BorderSide(color: colors.outlineVariant)),
      ),
      child: Material(
        color: colors.surface,
        child: SafeArea(
          child: isCompact ? _buildCompact(context) : _buildExpanded(context),
        ),
      ),
    );
  }

  Widget _buildCompact(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 15),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            _BrandMark(size: 42),
            const SizedBox(height: 20),
            Tooltip(
              message: 'Nouvelle conversation',
              child: IconButton.filled(
                onPressed: onNewConversation,
                icon: const Icon(Icons.add_rounded),
              ),
            ),
            const SizedBox(height: 18),
            _CompactNavigationButton(
              tooltip: 'Chat',
              icon: Icons.chat_bubble_rounded,
              selected: true,
              onPressed: _closeIfNeeded,
            ),
            _CompactNavigationButton(
              tooltip: 'Dashboard — indisponible actuellement',
              icon: Icons.space_dashboard_outlined,
              onPressed: onDashboard == null ? null : _closeAndDashboard,
            ),
            _CompactNavigationButton(
              tooltip: 'Historique — indisponible actuellement',
              icon: Icons.history_rounded,
              onPressed: onHistory == null ? null : _closeAndHistory,
            ),
            const SizedBox(height: 12),
            Tooltip(
              message: isDarkMode ? 'Mode sombre' : 'Mode clair',
              child: IconButton(
                onPressed: () => onThemeChanged(!isDarkMode),
                icon: Icon(isDarkMode ? Icons.dark_mode : Icons.light_mode),
              ),
            ),
            Tooltip(
              message: 'Paramètres',
              child: IconButton(
                onPressed: onSettings,
                icon: const Icon(Icons.tune_rounded),
              ),
            ),
            const SizedBox(height: 8),
            IconButton(
              tooltip: profileEmail ?? 'Profil',
              onPressed: onProfile,
              icon: const Icon(Icons.account_circle_outlined),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildExpanded(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 18, 16, 14),
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                const _BrandMark(size: 42),
                const SizedBox(width: 11),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'EMSI-ChatBot',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.w800,
                          letterSpacing: -0.2,
                        ),
                      ),
                      Text(
                        'ASSISTANT DOCUMENTAIRE',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.labelSmall?.copyWith(
                          color: colors.onSurfaceVariant,
                          letterSpacing: 0.55,
                          fontSize: 9,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 22),
            SizedBox(
              height: 48,
              child: FilledButton.icon(
                onPressed: () {
                  onNewConversation();
                  _closeIfNeeded();
                },
                icon: const Icon(Icons.add_rounded),
                label: const Text('Nouvelle conversation'),
                style: FilledButton.styleFrom(
                  alignment: Alignment.centerLeft,
                  padding: const EdgeInsets.symmetric(horizontal: 14),
                ),
              ),
            ),
            const SizedBox(height: 22),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 10),
              child: Text(
                'ESPACE',
                style: theme.textTheme.labelSmall?.copyWith(
                  color: colors.onSurfaceVariant,
                  letterSpacing: 1.1,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
            const SizedBox(height: 7),
            _NavigationEntry(
              title: 'Dashboard',
              icon: Icons.space_dashboard_outlined,
              selected:
                  activeConversationId == null &&
                  onDashboard != null &&
                  !showArchived &&
                  !favoritesOnly,
              unavailable: onDashboard == null,
              onTap: _closeAndDashboard,
            ),
            _NavigationEntry(
              title: 'Historique',
              icon: Icons.history_rounded,
              selected: onHistory != null && activeConversationId == null,
              unavailable: onHistory == null,
              onTap: _closeAndHistory,
            ),
            _NavigationEntry(
              title: 'Favoris',
              icon: Icons.star_outline_rounded,
              selected: favoritesOnly,
              unavailable: onFavorites == null,
              onTap: _closeAndFavorites,
            ),
            if (onSearchChanged != null) ...[
              const SizedBox(height: 10),
              TextField(
                key: const ValueKey('conversation-search'),
                controller: searchController,
                onChanged: onSearchChanged,
                decoration: InputDecoration(
                  isDense: true,
                  hintText: 'Rechercher',
                  prefixIcon: const Icon(Icons.search_rounded, size: 19),
                  suffixIcon: searchQuery.isEmpty
                      ? null
                      : IconButton(
                          tooltip: 'Effacer la recherche',
                          onPressed: () => onSearchChanged?.call(''),
                          icon: const Icon(Icons.close_rounded, size: 18),
                        ),
                ),
              ),
              const SizedBox(height: 7),
              Wrap(
                spacing: 6,
                children: [
                  ChoiceChip(
                    label: const Text('Actives'),
                    selected: !showArchived,
                    onSelected: (_) => onArchivedChanged?.call(false),
                    visualDensity: VisualDensity.compact,
                  ),
                  ChoiceChip(
                    label: const Text('Archivées'),
                    selected: showArchived,
                    onSelected: (_) => onArchivedChanged?.call(true),
                    visualDensity: VisualDensity.compact,
                  ),
                ],
              ),
              const SizedBox(height: 5),
              SizedBox(height: 210, child: _buildConversationList()),
            ],
            const SizedBox(height: 18),
            _AssistantInfoCard(),
            const SizedBox(height: 10),
            SwitchListTile.adaptive(
              contentPadding: const EdgeInsets.symmetric(horizontal: 9),
              dense: true,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(13),
              ),
              title: const Text('Mode sombre'),
              secondary: Icon(
                isDarkMode ? Icons.dark_mode : Icons.light_mode,
                size: 20,
              ),
              value: isDarkMode,
              onChanged: onThemeChanged,
            ),
            ListTile(
              dense: true,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(13),
              ),
              leading: const Icon(Icons.tune_rounded, size: 20),
              title: const Text('Paramètres'),
              trailing: const Icon(Icons.chevron_right_rounded, size: 18),
              onTap: () {
                onSettings();
                _closeIfNeeded();
              },
            ),
            const SizedBox(height: 8),
            Material(
              color: colors.surfaceContainerLow,
              borderRadius: BorderRadius.circular(15),
              child: InkWell(
                onTap: onProfile,
                borderRadius: BorderRadius.circular(15),
                child: Container(
                  padding: const EdgeInsets.all(11),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(15),
                    border: Border.all(color: colors.outlineVariant),
                  ),
                  child: Row(
                    children: [
                      CircleAvatar(
                        radius: 16,
                        backgroundColor: colors.surfaceContainerHigh,
                        child: Icon(
                          Icons.person_outline_rounded,
                          size: 18,
                          color: colors.onSurfaceVariant,
                        ),
                      ),
                      const SizedBox(width: 9),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              key: const ValueKey('sidebar-profile-email'),
                              profileEmail ?? 'Profil indisponible',
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: theme.textTheme.labelLarge?.copyWith(
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                            Text(
                              profileEmail == null
                                  ? 'Connectez-vous'
                                  : 'Compte Supabase',
                              style: theme.textTheme.labelSmall?.copyWith(
                                color: colors.onSurfaceVariant,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ConversationEntry extends StatelessWidget {
  const _ConversationEntry({
    required this.conversation,
    required this.selected,
    this.onTap,
    this.onRename,
    this.onDelete,
    this.onArchive,
    this.onFavorite,
  });

  final ConversationSummary conversation;
  final bool selected;
  final VoidCallback? onTap;
  final VoidCallback? onRename;
  final VoidCallback? onDelete;
  final VoidCallback? onArchive;
  final VoidCallback? onFavorite;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Material(
      key: ValueKey('sidebar-conversation-${conversation.id}'),
      color: selected ? colors.primaryContainer : Colors.transparent,
      borderRadius: BorderRadius.circular(12),
      child: ListTile(
        dense: true,
        selected: selected,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        leading: Icon(
          conversation.isFavorite ? Icons.star_rounded : Icons.chat_outlined,
          size: 18,
          color: conversation.isFavorite ? colors.tertiary : null,
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
        onTap: onTap,
        trailing: PopupMenuButton<String>(
          tooltip: 'Actions sur la conversation',
          onSelected: (action) {
            switch (action) {
              case 'rename':
                onRename?.call();
                break;
              case 'favorite':
                onFavorite?.call();
                break;
              case 'archive':
                onArchive?.call();
                break;
              case 'delete':
                onDelete?.call();
                break;
            }
          },
          itemBuilder: (context) => [
            const PopupMenuItem(
              value: 'rename',
              child: ListTile(
                dense: true,
                leading: Icon(Icons.edit_outlined),
                title: Text('Renommer'),
              ),
            ),
            PopupMenuItem(
              value: 'favorite',
              child: ListTile(
                dense: true,
                leading: Icon(
                  conversation.isFavorite
                      ? Icons.star_outline_rounded
                      : Icons.star_rounded,
                ),
                title: Text(
                  conversation.isFavorite
                      ? 'Retirer des favoris'
                      : 'Ajouter aux favoris',
                ),
              ),
            ),
            PopupMenuItem(
              value: 'archive',
              child: ListTile(
                dense: true,
                leading: Icon(
                  conversation.isArchived
                      ? Icons.unarchive_outlined
                      : Icons.archive_outlined,
                ),
                title: Text(conversation.isArchived ? 'Restaurer' : 'Archiver'),
              ),
            ),
            const PopupMenuItem(
              value: 'delete',
              child: ListTile(
                dense: true,
                leading: Icon(Icons.delete_outline_rounded),
                title: Text('Supprimer'),
              ),
            ),
          ],
          icon: const Icon(Icons.more_horiz_rounded, size: 19),
        ),
      ),
    );
  }
}

class _BrandMark extends StatelessWidget {
  const _BrandMark({required this.size});

  final double size;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: colors.primary,
        borderRadius: BorderRadius.circular(size * 0.34),
        boxShadow: [
          BoxShadow(
            color: colors.primary.withValues(alpha: 0.18),
            blurRadius: 12,
            offset: const Offset(0, 5),
          ),
        ],
      ),
      child: Icon(
        Icons.school_rounded,
        color: colors.onPrimary,
        size: size * 0.52,
      ),
    );
  }
}

class _CompactNavigationButton extends StatelessWidget {
  const _CompactNavigationButton({
    required this.tooltip,
    required this.icon,
    this.selected = false,
    this.onPressed,
  });

  final String tooltip;
  final IconData icon;
  final bool selected;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Tooltip(
      message: tooltip,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 3),
        child: IconButton(
          onPressed: onPressed,
          style: IconButton.styleFrom(
            backgroundColor: selected ? colors.primaryContainer : null,
            foregroundColor: selected
                ? colors.primary
                : colors.onSurfaceVariant,
            disabledForegroundColor: colors.onSurfaceVariant.withValues(
              alpha: 0.45,
            ),
            fixedSize: const Size(44, 44),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(14),
            ),
          ),
          icon: Icon(icon, size: 20),
        ),
      ),
    );
  }
}

class _NavigationEntry extends StatelessWidget {
  const _NavigationEntry({
    required this.title,
    required this.icon,
    this.selected = false,
    this.unavailable = false,
    this.onTap,
  });

  final String title;
  final IconData icon;
  final bool selected;
  final bool unavailable;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Tooltip(
      message: unavailable ? '$title — indisponible actuellement' : title,
      child: ListTile(
        key: ValueKey('navigation-${title.toLowerCase()}'),
        dense: true,
        selected: selected,
        enabled: !unavailable,
        selectedTileColor: colors.primaryContainer,
        selectedColor: colors.primary,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(13)),
        leading: Icon(icon, size: 20),
        title: Text(title),
        trailing: unavailable
            ? Text(
                'Bientôt',
                style: Theme.of(context).textTheme.labelSmall
                    ?.copyWith(color: colors.onSurfaceVariant),
              )
            : null,
        onTap: onTap,
      ),
    );
  }
}

class _AssistantInfoCard extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;
    return Container(
      padding: const EdgeInsets.all(13),
      decoration: BoxDecoration(
        color: colors.primaryContainer.withValues(alpha: 0.72),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: colors.primary.withValues(alpha: 0.12)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.auto_awesome_rounded, size: 17, color: colors.primary),
              const SizedBox(width: 7),
              Expanded(
                child: Text(
                  'VOTRE ASSISTANT',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.labelLarge?.copyWith(
                    color: colors.onPrimaryContainer,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            'Explorez la brochure EMSI avec des réponses documentées et des citations PDF.',
            style: theme.textTheme.bodySmall?.copyWith(
              color: colors.onPrimaryContainer,
              height: 1.45,
            ),
          ),
          const SizedBox(height: 10),
          const Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              _FeatureTag(label: 'RAG'),
              _FeatureTag(label: 'PDF'),
              _FeatureTag(label: 'Images optionnelles'),
            ],
          ),
        ],
      ),
    );
  }
}

class _FeatureTag extends StatelessWidget {
  const _FeatureTag({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: colors.surface.withValues(alpha: 0.75),
        borderRadius: BorderRadius.circular(9),
      ),
      child: Text(
        label,
        style: Theme.of(context).textTheme.labelSmall
            ?.copyWith(color: colors.onSurface, fontWeight: FontWeight.w600),
      ),
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
        constraints: const BoxConstraints(maxWidth: 790),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(22, 34, 22, 28),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 11,
                  vertical: 7,
                ),
                decoration: BoxDecoration(
                  color: colors.primaryContainer,
                  borderRadius: BorderRadius.circular(30),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      Icons.auto_awesome_rounded,
                      size: 15,
                      color: colors.primary,
                    ),
                    const SizedBox(width: 7),
                    Flexible(
                      child: Text(
                        'ASSISTANT DOCUMENTAIRE EMSI',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.labelSmall?.copyWith(
                          color: colors.onPrimaryContainer,
                          letterSpacing: 0.7,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 20),
              Text(
                'Bonjour, que souhaitez-vous découvrir ?',
                style: theme.textTheme.headlineMedium?.copyWith(
                  fontWeight: FontWeight.w800,
                  height: 1.15,
                  letterSpacing: -0.7,
                ),
              ),
              const SizedBox(height: 11),
              ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 650),
                child: Text(
                  'Posez une question sur les campus, les formations ou les informations de la brochure EMSI. Les réponses s’appuient sur les passages retrouvés et affichent leurs références.',
                  style: theme.textTheme.bodyLarge?.copyWith(
                    color: colors.onSurfaceVariant,
                    height: 1.6,
                  ),
                ),
              ),
              const SizedBox(height: 25),
              Wrap(
                spacing: 9,
                runSpacing: 8,
                children: const [
                  _WelcomeFeature(
                    icon: Icons.menu_book_outlined,
                    label: 'Recherche dans la brochure',
                  ),
                  _WelcomeFeature(
                    icon: Icons.format_quote_rounded,
                    label: 'Citations PDF',
                  ),
                  _WelcomeFeature(
                    icon: Icons.image_search_outlined,
                    label: 'Images en option',
                  ),
                ],
              ),
              const SizedBox(height: 29),
              Text(
                'Pour commencer',
                style: theme.textTheme.titleSmall?.copyWith(
                  fontWeight: FontWeight.w800,
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
                            key: ValueKey('welcome-suggestion-$index'),
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

class _WelcomeFeature extends StatelessWidget {
  const _WelcomeFeature({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: colors.outlineVariant),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: colors.primary, size: 16),
          const SizedBox(width: 7),
          Flexible(
            child: Text(
              label,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(context).textTheme.labelMedium,
            ),
          ),
        ],
      ),
    );
  }
}

class _SuggestionCard extends StatelessWidget {
  const _SuggestionCard({
    super.key,
    required this.text,
    required this.icon,
    required this.onTap,
  });

  final String text;
  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(15),
          child: Row(
            children: [
              Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  color: colors.primaryContainer,
                  borderRadius: BorderRadius.circular(11),
                ),
                child: Icon(icon, color: colors.primary, size: 19),
              ),
              const SizedBox(width: 11),
              Expanded(child: Text(text, style: theme.textTheme.bodyMedium)),
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
    required this.isPickingImage,
    required this.includeImages,
    required this.onIncludeImagesChanged,
    required this.onSend,
    required this.onPickImage,
    required this.onRemoveImage,
    required this.selectedImage,
  });

  final TextEditingController controller;
  final bool isLoading;
  final bool isPickingImage;
  final bool includeImages;
  final ValueChanged<bool> onIncludeImagesChanged;
  final VoidCallback onSend;
  final VoidCallback? onPickImage;
  final VoidCallback onRemoveImage;
  final SelectedChatImage? selectedImage;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;
    return Material(
      color: colors.surface,
      child: SafeArea(
        top: false,
        child: Container(
          padding: const EdgeInsets.fromLTRB(14, 12, 14, 10),
          decoration: BoxDecoration(
            border: Border(top: BorderSide(color: colors.outlineVariant)),
          ),
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 920),
              child: LayoutBuilder(
                builder: (context, constraints) {
                  final compact = constraints.maxWidth < 400;
                  final imageButton = Tooltip(
                    message: 'Joindre une image JPEG, PNG ou WebP (5 Mo max.)',
                    child: IconButton.filledTonal(
                      key: const ValueKey('attach-image-button'),
                      onPressed: isLoading || isPickingImage
                          ? null
                          : onPickImage,
                      icon: isPickingImage
                          ? const SizedBox(
                              width: 19,
                              height: 19,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.add_photo_alternate_outlined),
                    ),
                  );
                  return Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      if (selectedImage != null)
                        Align(
                          alignment: Alignment.centerLeft,
                          child: Container(
                            margin: const EdgeInsets.only(bottom: 8),
                            padding: const EdgeInsets.all(7),
                            decoration: BoxDecoration(
                              color: colors.surfaceContainerLow,
                              borderRadius: BorderRadius.circular(12),
                              border: Border.all(color: colors.outlineVariant),
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                ClipRRect(
                                  borderRadius: BorderRadius.circular(8),
                                  child: Image.memory(
                                    selectedImage!.bytes,
                                    width: 54,
                                    height: 54,
                                    fit: BoxFit.cover,
                                  ),
                                ),
                                const SizedBox(width: 9),
                                ConstrainedBox(
                                  constraints: const BoxConstraints(
                                    maxWidth: 140,
                                  ),
                                  child: Text(
                                    selectedImage!.fileName,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                ),
                                IconButton(
                                  key: const ValueKey('remove-selected-image'),
                                  tooltip: 'Retirer l’image',
                                  onPressed: isLoading ? null : onRemoveImage,
                                  icon: const Icon(Icons.close_rounded),
                                ),
                              ],
                            ),
                          ),
                        ),
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          if (!compact) imageButton,
                          if (!compact) const SizedBox(width: 7),
                          Expanded(
                            child: TextField(
                              controller: controller,
                              enabled: !isLoading,
                              minLines: 1,
                              maxLines: 5,
                              textCapitalization: TextCapitalization.sentences,
                              textInputAction: TextInputAction.send,
                              onSubmitted: (_) => onSend(),
                              decoration: const InputDecoration(
                                hintText: "Posez votre question sur l'EMSI...",
                                prefixIcon: Icon(
                                  Icons.chat_bubble_outline_rounded,
                                ),
                              ),
                            ),
                          ),
                          const SizedBox(width: 8),
                          Tooltip(
                            message: 'Envoyer',
                            child: SizedBox(
                              height: 52,
                              width: 52,
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
                      if (compact)
                        Align(
                          alignment: Alignment.centerLeft,
                          child: imageButton,
                        ),
                      const SizedBox(height: 8),
                      Wrap(
                        alignment: WrapAlignment.start,
                        crossAxisAlignment: WrapCrossAlignment.center,
                        spacing: 7,
                        runSpacing: 2,
                        children: [
                          _ModeChip(
                            label: 'Réponse IA activée',
                            icon: Icons.auto_awesome_rounded,
                          ),
                          Tooltip(
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
                              onSelected: isLoading
                                  ? null
                                  : onIncludeImagesChanged,
                              visualDensity: VisualDensity.compact,
                            ),
                          ),
                          Text(
                            'L’ajout d’images sera disponible dans une prochaine version.',
                            style: theme.textTheme.labelSmall?.copyWith(
                              color: colors.onSurfaceVariant,
                            ),
                          ),
                        ],
                      ),
                    ],
                  );
                },
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _ModeChip extends StatelessWidget {
  const _ModeChip({required this.label, required this.icon});

  final String label;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 7),
      decoration: BoxDecoration(
        color: colors.primaryContainer,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 15, color: colors.primary),
          const SizedBox(width: 6),
          Text(
            label,
            style: Theme.of(context).textTheme.labelSmall?.copyWith(
              color: colors.onPrimaryContainer,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }
}

import 'dart:async';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:supabase_flutter/supabase_flutter.dart';

import '../models/chat_models.dart';
import '../models/conversation_models.dart';
import '../services/chat_api_service.dart';
import '../services/conversation_repository.dart';
import '../services/image_selection_service.dart';
import '../widgets/chat_message_bubble.dart';
import '../widgets/chat_shell_widgets.dart';
import '../widgets/personal_dashboard.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({
    super.key,
    this.client,
    this.apiBaseUrl,
    this.profileEmail,
    this.onProfile,
    this.supabaseClient,
    this.conversationRepository,
    this.accessTokenProvider,
    this.imagePicker,
    this.themeMode = ThemeMode.light,
    this.onThemeModeChanged,
  });

  final http.Client? client;
  final String? apiBaseUrl;
  final String? profileEmail;
  final VoidCallback? onProfile;
  final SupabaseClient? supabaseClient;
  final ConversationRepository? conversationRepository;
  final String? Function()? accessTokenProvider;
  final ChatImagePicker? imagePicker;
  final ThemeMode themeMode;
  final ValueChanged<ThemeMode>? onThemeModeChanged;

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final TextEditingController _controller = TextEditingController();
  final TextEditingController _searchController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  final List<ChatMessage> _messages = [];
  final List<ConversationSummary> _conversations = [];
  final ConversationMemory _conversationMemory = ConversationMemory();
  late final ConversationRepository? _repository =
      widget.conversationRepository ??
      (widget.supabaseClient == null
          ? null
          : SupabaseConversationRepository(
              widget.supabaseClient!,
              imageBaseUrl: widget.apiBaseUrl,
            ));
  late final ChatApiService _api = ChatApiService(
    client: widget.client,
    baseUrl: widget.apiBaseUrl,
  );

  bool _isLoading = false;
  bool _isPickingImage = false;
  bool _includeImages = false;
  bool _isLoadingConversations = false;
  bool _conversationReloadQueued = false;
  bool _isCreatingConversation = false;
  bool _isLoadingMessages = false;
  bool _showArchived = false;
  bool _favoritesOnly = false;
  bool _dashboardVisible = true;
  bool _transientChatVisible = false;
  bool _hasMoreConversations = false;
  String _searchQuery = '';
  String? _activeConversationId;
  DashboardStats? _dashboardStats;
  String? _conversationsError;
  Timer? _searchDebounce;
  late final ChatImagePicker _imagePicker =
      widget.imagePicker ?? PlatformChatImagePicker();
  SelectedChatImage? _selectedImage;

  static const String _screenKey = 'chat-workspace';

  bool get _isDarkMode => widget.themeMode == ThemeMode.dark;

  @override
  void initState() {
    super.initState();
    if (_repository != null) _loadConversations();
  }

  @override
  void dispose() {
    _api.dispose();
    _searchDebounce?.cancel();
    _controller.dispose();
    _searchController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _resetConversation() {
    if (_isLoading) return;
    if (_repository != null) {
      _createConversation();
      return;
    }
    _controller.clear();
    _conversationMemory.clear();
    setState(_messages.clear);
    _scrollToBottom();
  }

  Future<void> _createConversation() async {
    final repository = _repository;
    if (repository == null || _isCreatingConversation) return;
    setState(() {
      _isCreatingConversation = true;
      _conversationsError = null;
    });
    try {
      final created = await repository.createConversation();
      if (!mounted) return;
      setState(() {
        _activeConversationId = created.id;
        _selectedImage = null;
        _messages.clear();
        _conversationMemory.clear();
        _showArchived = false;
        _favoritesOnly = false;
        _dashboardVisible = false;
        _transientChatVisible = false;
        _isCreatingConversation = false;
      });
      await _loadConversations();
    } on ConversationRepositoryException catch (error) {
      if (mounted) _showNotice(error.message);
    } finally {
      if (mounted) setState(() => _isCreatingConversation = false);
    }
  }

  Future<void> _loadConversations({
    bool loadStats = true,
    bool append = false,
  }) async {
    final repository = _repository;
    if (repository == null) return;
    if (_isLoadingConversations) {
      _conversationReloadQueued = true;
      return;
    }
    final offset = append ? _conversations.length : 0;
    setState(() {
      _isLoadingConversations = true;
      _conversationsError = null;
    });
    try {
      final rows = await repository.listConversations(
        query: _searchQuery,
        archived: _showArchived,
        favoritesOnly: _favoritesOnly,
        offset: offset,
      );
      final stats = loadStats ? await repository.loadStats() : _dashboardStats;
      if (!mounted) return;
      setState(() {
        if (append) {
          _conversations.addAll(rows);
        } else {
          _conversations
            ..clear()
            ..addAll(rows);
        }
        _hasMoreConversations = rows.length == 30;
        _dashboardStats = stats;
      });
    } on ConversationRepositoryException catch (error) {
      if (mounted) setState(() => _conversationsError = error.message);
    } finally {
      if (mounted) {
        setState(() => _isLoadingConversations = false);
        if (_conversationReloadQueued) {
          _conversationReloadQueued = false;
          scheduleMicrotask(() => _loadConversations(loadStats: false));
        }
      }
    }
  }

  void _loadMoreConversations() {
    if (!_isLoadingConversations && _hasMoreConversations) {
      _loadConversations(loadStats: false, append: true);
    }
  }

  void _onSearchChanged(String value) {
    _searchQuery = value;
    if (value.isEmpty && _searchController.text.isNotEmpty) {
      _searchController.clear();
    }
    _searchDebounce?.cancel();
    _searchDebounce = Timer(
      const Duration(milliseconds: 300),
      () => _loadConversations(loadStats: false),
    );
    setState(() {});
  }

  void _showDashboard() {
    setState(() {
      _activeConversationId = null;
      _dashboardVisible = true;
      _transientChatVisible = false;
      _showArchived = false;
      _favoritesOnly = false;
      _messages.clear();
      _conversationMemory.clear();
    });
    _loadConversations();
  }

  void _showHistory() {
    setState(() {
      _activeConversationId = null;
      _dashboardVisible = false;
      _transientChatVisible = false;
      _showArchived = false;
      _favoritesOnly = false;
      _messages.clear();
      _conversationMemory.clear();
    });
    _loadConversations();
  }

  void _showFavorites() {
    setState(() {
      _activeConversationId = null;
      _dashboardVisible = false;
      _transientChatVisible = false;
      _showArchived = false;
      _favoritesOnly = true;
      _messages.clear();
      _conversationMemory.clear();
    });
    _loadConversations(loadStats: false);
  }

  void _setArchivedFilter(bool value) {
    setState(() {
      _activeConversationId = null;
      _dashboardVisible = false;
      _transientChatVisible = false;
      _showArchived = value;
      _favoritesOnly = false;
      _messages.clear();
      _conversationMemory.clear();
    });
    _loadConversations(loadStats: false);
  }

  Future<void> _openConversation(ConversationSummary conversation) async {
    final repository = _repository;
    if (repository == null || _isLoading) return;
    setState(() {
      _isLoadingMessages = true;
      _conversationsError = null;
    });
    try {
      final messages = await repository.loadMessages(conversation.id);
      if (!mounted) return;
      _conversationMemory.clear();
      String? pendingQuestion;
      for (final message in messages) {
        if (message.isUser) {
          pendingQuestion = message.text;
        } else if (pendingQuestion != null && !message.isError) {
          _conversationMemory.recordExchange(pendingQuestion, message.text);
          pendingQuestion = null;
        }
      }
      setState(() {
        _activeConversationId = conversation.id;
        _dashboardVisible = false;
        _transientChatVisible = false;
        _messages
          ..clear()
          ..addAll(messages);
        _showArchived = false;
        _favoritesOnly = false;
      });
      _scrollToBottom();
    } on ConversationRepositoryException catch (error) {
      if (mounted) _showNotice(error.message);
    } finally {
      if (mounted) setState(() => _isLoadingMessages = false);
    }
  }

  Future<void> _renameConversation(ConversationSummary conversation) async {
    final title = await showDialog<String>(
      context: context,
      builder: (_) =>
          _RenameConversationDialog(initialTitle: conversation.title),
    );
    if (!mounted || title == null) return;
    final trimmed = title.trim();
    if (trimmed.isEmpty || trimmed.length > 120) {
      _showNotice('Le titre doit contenir entre 1 et 120 caractères.');
      return;
    }
    try {
      await _repository!.rename(conversation.id, trimmed);
      if (!mounted) return;
      await _loadConversations();
    } on ConversationRepositoryException catch (error) {
      if (mounted) _showNotice(error.message);
    }
  }

  Future<void> _deleteConversation(ConversationSummary conversation) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Supprimer la conversation ?'),
        content: const Text(
          'La conversation et ses messages seront supprimés définitivement.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('Annuler'),
          ),
          FilledButton.tonal(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('Supprimer'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await _repository!.delete(conversation.id);
      if (_activeConversationId == conversation.id) _showDashboard();
      await _loadConversations();
    } on ConversationCleanupException catch (error) {
      if (mounted) {
        await _loadConversations();
        _showNotice(error.message);
      }
    } on ConversationRepositoryException catch (error) {
      if (mounted) _showNotice(error.message);
    }
  }

  Future<void> _toggleArchive(ConversationSummary conversation) async {
    try {
      await _repository!.setArchived(conversation.id, !conversation.isArchived);
      if (_activeConversationId == conversation.id &&
          !conversation.isArchived) {
        _showDashboard();
      }
      await _loadConversations();
    } on ConversationRepositoryException catch (error) {
      if (mounted) _showNotice(error.message);
    }
  }

  Future<void> _toggleFavorite(ConversationSummary conversation) async {
    try {
      await _repository!.setFavorite(conversation.id, !conversation.isFavorite);
      await _loadConversations();
    } on ConversationRepositoryException catch (error) {
      if (mounted) _showNotice(error.message);
    }
  }

  void _showNotice(String text) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(text)));
  }

  Future<void> _sendMessage([String? suggestedQuestion]) async {
    await _submitQuestion(
      suggestedQuestion ?? _controller.text,
      attachment: _selectedImage,
    );
  }

  Future<void> _retryQuestion(
    String question,
    String? requestId, {
    SelectedChatImage? attachment,
  }) async {
    await _submitQuestion(
      question,
      retry: true,
      retryRequestId: requestId,
      attachment: attachment,
    );
  }

  Future<void> _pickImage() async {
    final token =
        widget.accessTokenProvider?.call() ??
        widget.supabaseClient?.auth.currentSession?.accessToken;
    if (_repository == null || token == null || token.isEmpty) {
      _showNotice('Connectez-vous pour joindre une image à une conversation.');
      return;
    }
    setState(() => _isPickingImage = true);
    try {
      final image = await _imagePicker.pickImage();
      if (!mounted || image == null) return;
      setState(() => _selectedImage = image);
    } on FormatException catch (error) {
      if (mounted) _showNotice(error.message);
    } catch (_) {
      if (mounted) _showNotice('Impossible de sélectionner cette image.');
    } finally {
      if (mounted) setState(() => _isPickingImage = false);
    }
  }

  Future<void> _submitQuestion(
    String rawQuestion, {
    bool retry = false,
    String? retryRequestId,
    SelectedChatImage? attachment,
  }) async {
    if (_isLoading) return;
    final question = rawQuestion.trim();
    if (question.isEmpty) return;
    final requestId = retryRequestId ?? _newRequestId();

    _controller.clear();
    setState(() {
      if (_repository != null && _activeConversationId == null) {
        _dashboardVisible = false;
        _transientChatVisible = true;
      }
      if (retry) {
        _messages.removeWhere(
          (message) =>
              message.isError &&
              message.retryQuestion == question &&
              message.retryRequestId == retryRequestId,
        );
      } else {
        _messages.add(
          ChatMessage(
            text: question,
            isUser: true,
            images: attachment == null
                ? const []
                : [
                    ChatImage(
                      url: '',
                      bytes: attachment.bytes,
                      mimeType: attachment.mimeType,
                    ),
                  ],
          ),
        );
        _selectedImage = null;
      }
      _isLoading = true;
    });
    _scrollToBottom();

    try {
      if (_repository != null && _activeConversationId == null) {
        final conversation = await _repository.createConversation();
        if (!mounted) return;
        setState(() => _activeConversationId = conversation.id);
      }
      final response = await _api.sendQuestion(
        question: question,
        history: _conversationMemory.messages,
        includeImages: _includeImages,
        conversationId: _activeConversationId,
        accessToken:
            widget.accessTokenProvider?.call() ??
            widget.supabaseClient?.auth.currentSession?.accessToken,
        requestId: requestId,
        attachment: attachment,
      );
      if (!mounted) return;
      setState(() {
        _conversationMemory.recordExchange(question, response.answer);
        _messages.add(
          ChatMessage(
            text: response.answer,
            isUser: false,
            sources: response.sources,
            images: response.images,
          ),
        );
      });
      if (_repository != null) await _loadConversations();
    } on ChatRequestException catch (error) {
      _appendError(error.message, question, requestId, attachment);
    } on ConversationRepositoryException catch (error) {
      _appendError(error.message, question, requestId, attachment);
    } catch (_) {
      _appendError(
        'Une erreur inattendue est survenue. Réessayez.',
        question,
        requestId,
        attachment,
      );
    } finally {
      if (mounted) {
        setState(() => _isLoading = false);
        _scrollToBottom();
      }
    }
  }

  void _appendError(
    String text,
    String question,
    String requestId,
    SelectedChatImage? attachment,
  ) {
    if (!mounted) return;
    setState(() {
      _messages.add(
        ChatMessage(
          text: text,
          isUser: false,
          isError: true,
          retryQuestion: question,
          retryRequestId: requestId,
          retryImageBytes: attachment?.bytes,
          retryImageMimeType: attachment?.mimeType,
        ),
      );
    });
  }

  String _newRequestId() {
    final bytes = List<int>.generate(16, (_) => Random.secure().nextInt(256));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    final hex = bytes
        .map((byte) => byte.toRadixString(16).padLeft(2, '0'))
        .join();
    return '${hex.substring(0, 8)}-${hex.substring(8, 12)}-'
        '${hex.substring(12, 16)}-${hex.substring(16, 20)}-${hex.substring(20)}';
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_scrollController.hasClients) return;
      _scrollController.animateTo(
        _scrollController.position.maxScrollExtent,
        duration: const Duration(milliseconds: 260),
        curve: Curves.easeOutCubic,
      );
    });
  }

  void _changeTheme(bool dark) {
    widget.onThemeModeChanged?.call(dark ? ThemeMode.dark : ThemeMode.light);
  }

  Future<void> _showSettings() async {
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (context) => StatefulBuilder(
        builder: (context, setSheetState) => SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(18, 8, 18, 24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Paramètres',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: 10),
                SwitchListTile.adaptive(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Mode sombre'),
                  secondary: const Icon(Icons.dark_mode_outlined),
                  value: _isDarkMode,
                  onChanged: (value) {
                    _changeTheme(value);
                    setSheetState(() {});
                  },
                ),
                SwitchListTile.adaptive(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Recherche d’images'),
                  subtitle: const Text(
                    'Recherche facultative dans les images indexées.',
                  ),
                  secondary: const Icon(Icons.image_search_outlined),
                  value: _includeImages,
                  onChanged: (value) {
                    setState(() => _includeImages = value);
                    setSheetState(() {});
                  },
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  AppSidebar _buildSidebar({bool compact = false, VoidCallback? onClose}) =>
      AppSidebar(
        isCompact: compact,
        isDarkMode: _isDarkMode,
        onNewConversation: _resetConversation,
        onThemeChanged: _changeTheme,
        onSettings: _showSettings,
        onClose: onClose,
        profileEmail: widget.profileEmail,
        onProfile: widget.onProfile,
        conversations: _conversations,
        activeConversationId: _activeConversationId,
        searchQuery: _searchQuery,
        searchController: _searchController,
        showArchived: _showArchived,
        favoritesOnly: _favoritesOnly,
        isLoadingConversations: _isLoadingConversations,
        hasMoreConversations: _hasMoreConversations,
        onDashboard: _repository == null ? null : _showDashboard,
        onHistory: _repository == null ? null : _showHistory,
        onFavorites: _repository == null ? null : _showFavorites,
        onSearchChanged: _repository == null ? null : _onSearchChanged,
        onArchivedChanged: _repository == null ? null : _setArchivedFilter,
        onOpenConversation: _repository == null ? null : _openConversation,
        onRenameConversation: _repository == null ? null : _renameConversation,
        onDeleteConversation: _repository == null ? null : _deleteConversation,
        onArchiveConversation: _repository == null ? null : _toggleArchive,
        onFavoriteConversation: _repository == null ? null : _toggleFavorite,
        onLoadMore: _loadMoreConversations,
      );

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    final desktop = width >= 1080;
    final tablet = width >= 720 && !desktop;
    final theme = Theme.of(context);
    return Scaffold(
      drawer: desktop || tablet
          ? null
          : Drawer(
              child: _buildSidebar(
                onClose: () => Navigator.of(context).maybePop(),
              ),
            ),
      appBar: AppBar(
        titleSpacing: desktop ? 24 : null,
        title: Row(
          children: [
            if (desktop) ...[
              Icon(
                Icons.auto_awesome_rounded,
                color: theme.colorScheme.secondary,
              ),
              const SizedBox(width: 10),
            ],
            Flexible(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'EMSI-ChatBot',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  Text(
                    'Assistant documentaire de la brochure EMSI',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.labelSmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
        actions: [
          if (width < 480)
            PopupMenuButton<String>(
              key: const ValueKey('mobile-account-menu'),
              tooltip: 'Compte et paramètres',
              onSelected: (value) {
                if (value == 'profile') widget.onProfile?.call();
                if (value == 'settings') _showSettings();
              },
              itemBuilder: (context) => [
                PopupMenuItem(
                  value: 'profile',
                  enabled: widget.onProfile != null,
                  child: const Text('Profil'),
                ),
                const PopupMenuItem(
                  value: 'settings',
                  child: Text('Paramètres'),
                ),
              ],
              icon: const Icon(Icons.more_vert_rounded),
            )
          else ...[
            IconButton(
              tooltip: 'Profil',
              onPressed: widget.onProfile,
              icon: const Icon(Icons.account_circle_outlined),
            ),
            IconButton(
              tooltip: 'Paramètres',
              onPressed: _showSettings,
              icon: const Icon(Icons.tune_rounded),
            ),
          ],
          IconButton(
            key: const ValueKey('appbar-new-conversation'),
            tooltip: 'Nouvelle conversation',
            onPressed: _isLoading ? null : _resetConversation,
            icon: const Icon(Icons.edit_square),
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: Row(
        children: [
          if (desktop)
            _buildSidebar()
          else if (tablet)
            _buildSidebar(compact: true),
          Expanded(child: _buildWorkspace()),
        ],
      ),
    );
  }

  Widget _buildWorkspace() {
    if (_repository != null &&
        _activeConversationId == null &&
        _dashboardVisible) {
      if (_isLoadingMessages) {
        return const Center(child: CircularProgressIndicator());
      }
      if (_dashboardVisible) {
        return PersonalDashboard(
          email: widget.profileEmail,
          stats: _dashboardStats,
          recentConversations: _conversations
              .where((conversation) => !conversation.isArchived)
              .take(5)
              .toList(growable: false),
          isLoading: _isLoadingConversations || _isCreatingConversation,
          errorMessage: _conversationsError,
          onNewConversation: _createConversation,
          onOpenConversation: _openConversation,
          onHistory: _showHistory,
          onRetry: () => _loadConversations(),
        );
      }
      if (!_transientChatVisible) return _buildHistoryWorkspace();
    }
    if (_isLoadingMessages) {
      return const Center(child: CircularProgressIndicator());
    }
    return Column(
      key: const ValueKey(_screenKey),
      children: [
        Expanded(
          child: _messages.isEmpty
              ? SingleChildScrollView(
                  child: WelcomePanel(onSuggestion: _sendMessage),
                )
              : ListView.builder(
                  controller: _scrollController,
                  padding: const EdgeInsets.symmetric(
                    horizontal: 18,
                    vertical: 24,
                  ),
                  itemCount: _messages.length + (_isLoading ? 1 : 0),
                  itemBuilder: (context, index) {
                    if (index == _messages.length) {
                      return const _LoadingMessage();
                    }
                    final message = _messages[index];
                    return Center(
                      key: ValueKey(
                        'chat-message-${message.isUser ? 'user' : 'assistant'}-$index',
                      ),
                      child: ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 900),
                        child: ChatMessageBubble(
                          message: message,
                          onRetry: message.retryQuestion == null
                              ? null
                              : () => _retryQuestion(
                                  message.retryQuestion!,
                                  message.retryRequestId,
                                  attachment: message.retryImageBytes == null
                                      ? null
                                      : SelectedChatImage(
                                          bytes: message.retryImageBytes!,
                                          mimeType:
                                              message.retryImageMimeType ??
                                              'image/jpeg',
                                          fileName: 'image',
                                        ),
                                ),
                        ),
                      ),
                    );
                  },
                ),
        ),
        ChatComposer(
          controller: _controller,
          isLoading: _isLoading,
          isPickingImage: _isPickingImage,
          includeImages: _includeImages,
          onIncludeImagesChanged: (value) =>
              setState(() => _includeImages = value),
          onSend: _sendMessage,
          selectedImage: _selectedImage,
          onPickImage: _pickImage,
          onRemoveImage: () => setState(() => _selectedImage = null),
        ),
      ],
    );
  }

  Widget _buildHistoryWorkspace() {
    final title = _favoritesOnly
        ? 'Conversations favorites'
        : _showArchived
        ? 'Conversations archivées'
        : 'Historique des conversations';
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 900),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(24, 26, 24, 14),
              child: Text(
                title,
                style: Theme.of(context).textTheme.headlineSmall
                    ?.copyWith(fontWeight: FontWeight.w800),
              ),
            ),
            if (_conversationsError != null)
              ListTile(
                leading: const Icon(Icons.error_outline),
                title: Text(_conversationsError!),
                trailing: TextButton(
                  onPressed: () => _loadConversations(),
                  child: const Text('Réessayer'),
                ),
              ),
            if (_isLoadingConversations && _conversations.isEmpty)
              const Expanded(child: Center(child: CircularProgressIndicator()))
            else if (_conversations.isEmpty)
              const Expanded(
                child: Center(child: Text('Aucune conversation à afficher.')),
              )
            else
              Expanded(
                child: ListView.builder(
                  padding: const EdgeInsets.symmetric(horizontal: 18),
                  itemCount:
                      _conversations.length + (_hasMoreConversations ? 1 : 0),
                  itemBuilder: (context, index) {
                    if (index == _conversations.length) {
                      return Center(
                        child: TextButton(
                          onPressed: _loadMoreConversations,
                          child: const Text('Charger plus'),
                        ),
                      );
                    }
                    final conversation = _conversations[index];
                    return Card(
                      child: ListTile(
                        leading: Icon(
                          conversation.isFavorite
                              ? Icons.star_rounded
                              : Icons.chat_outlined,
                        ),
                        title: Text(conversation.title),
                        subtitle: Text(
                          conversation.lastMessage ?? 'Aucun message',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        trailing: Text('${conversation.messageCount} messages'),
                        onTap: () => _openConversation(conversation),
                      ),
                    );
                  },
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _RenameConversationDialog extends StatefulWidget {
  const _RenameConversationDialog({required this.initialTitle});

  final String initialTitle;

  @override
  State<_RenameConversationDialog> createState() =>
      _RenameConversationDialogState();
}

class _RenameConversationDialogState extends State<_RenameConversationDialog> {
  late final TextEditingController _controller;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.initialTitle);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Renommer la conversation'),
    content: TextField(
      key: const ValueKey('rename-title-field'),
      controller: _controller,
      autofocus: true,
      maxLength: 120,
      decoration: const InputDecoration(labelText: 'Titre'),
      onSubmitted: (value) => Navigator.of(context).pop(value),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.of(context).pop(),
        child: const Text('Annuler'),
      ),
      FilledButton(
        onPressed: () => Navigator.of(context).pop(_controller.text),
        child: const Text('Enregistrer'),
      ),
    ],
  );
}

class _LoadingMessage extends StatelessWidget {
  const _LoadingMessage();

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 900),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 14),
          child: Row(
            children: [
              SizedBox(
                width: 17,
                height: 17,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: colors.primary,
                  semanticsLabel: 'Recherche dans la brochure en cours',
                ),
              ),
              const SizedBox(width: 12),
              Text(
                'Recherche dans la brochure EMSI…',
                style: Theme.of(context).textTheme.bodySmall
                    ?.copyWith(color: colors.onSurfaceVariant),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

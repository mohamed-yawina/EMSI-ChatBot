import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import '../models/chat_models.dart';
import '../services/chat_api_service.dart';
import '../widgets/chat_message_bubble.dart';
import '../widgets/chat_shell_widgets.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({
    super.key,
    this.client,
    this.apiBaseUrl,
    this.themeMode = ThemeMode.light,
    this.onThemeModeChanged,
  });

  final http.Client? client;
  final String? apiBaseUrl;
  final ThemeMode themeMode;
  final ValueChanged<ThemeMode>? onThemeModeChanged;

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final TextEditingController _controller = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  final List<ChatMessage> _messages = [];
  final ConversationMemory _conversationMemory = ConversationMemory();
  late final ChatApiService _api = ChatApiService(
    client: widget.client,
    baseUrl: widget.apiBaseUrl,
  );

  bool _isLoading = false;
  bool _includeImages = false;

  static const String _screenKey = 'chat-workspace';

  bool get _isDarkMode => widget.themeMode == ThemeMode.dark;

  @override
  void dispose() {
    _api.dispose();
    _controller.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _resetConversation() {
    if (_isLoading) return;
    _controller.clear();
    _conversationMemory.clear();
    setState(_messages.clear);
    _scrollToBottom();
  }

  Future<void> _sendMessage([String? suggestedQuestion]) async {
    await _submitQuestion(suggestedQuestion ?? _controller.text);
  }

  Future<void> _retryQuestion(String question) async {
    await _submitQuestion(question, retry: true);
  }

  Future<void> _submitQuestion(String rawQuestion, {bool retry = false}) async {
    if (_isLoading) return;
    final question = rawQuestion.trim();
    if (question.isEmpty) return;

    _controller.clear();
    setState(() {
      if (retry) {
        _messages.removeWhere(
          (message) => message.isError && message.retryQuestion == question,
        );
      } else {
        _messages.add(ChatMessage(text: question, isUser: true));
      }
      _isLoading = true;
    });
    _scrollToBottom();

    try {
      final response = await _api.sendQuestion(
        question: question,
        history: _conversationMemory.messages,
        includeImages: _includeImages,
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
    } on ChatRequestException catch (error) {
      _appendError(error.message, question);
    } catch (_) {
      _appendError('Une erreur inattendue est survenue. Réessayez.', question);
    } finally {
      if (mounted) {
        setState(() => _isLoading = false);
        _scrollToBottom();
      }
    }
  }

  void _appendError(String text, String question) {
    if (!mounted) return;
    setState(() {
      _messages.add(
        ChatMessage(
          text: text,
          isUser: false,
          isError: true,
          retryQuestion: question,
        ),
      );
    });
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

  @override
  Widget build(BuildContext context) {
    final desktop = MediaQuery.sizeOf(context).width >= 1080;
    final theme = Theme.of(context);
    return Scaffold(
      drawer: desktop
          ? null
          : Drawer(
              child: AppSidebar(
                isDarkMode: _isDarkMode,
                onNewConversation: _resetConversation,
                onThemeChanged: _changeTheme,
                onSettings: _showSettings,
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
                  const Text('EMSI-ChatBot'),
                  Text(
                    'Assistant documentaire de la brochure EMSI',
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
          IconButton(
            tooltip: 'Paramètres',
            onPressed: _showSettings,
            icon: const Icon(Icons.tune_rounded),
          ),
          IconButton(
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
            AppSidebar(
              isDarkMode: _isDarkMode,
              onNewConversation: _resetConversation,
              onThemeChanged: _changeTheme,
              onSettings: _showSettings,
            ),
          Expanded(child: _buildWorkspace()),
        ],
      ),
    );
  }

  Widget _buildWorkspace() => Column(
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
                  if (index == _messages.length) return const _LoadingMessage();
                  final message = _messages[index];
                  return Center(
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 900),
                      child: ChatMessageBubble(
                        message: message,
                        onRetry: message.retryQuestion == null
                            ? null
                            : () => _retryQuestion(message.retryQuestion!),
                      ),
                    ),
                  );
                },
              ),
      ),
      ChatComposer(
        controller: _controller,
        isLoading: _isLoading,
        includeImages: _includeImages,
        onIncludeImagesChanged: (value) =>
            setState(() => _includeImages = value),
        onSend: _sendMessage,
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
                  color: colors.secondary,
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

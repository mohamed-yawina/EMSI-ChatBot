import 'package:emsi_chatbot/models/chat_models.dart';
import 'package:emsi_chatbot/models/conversation_models.dart';
import 'package:emsi_chatbot/services/conversation_repository.dart';

class FakeConversationRepository implements ConversationRepository {
  FakeConversationRepository({
    List<ConversationSummary> initialConversations = const [],
    Map<String, List<ChatMessage>> initialMessages = const {},
    this.stats = const DashboardStats(
      conversationCount: 0,
      messageCount: 0,
      favoriteCount: 0,
    ),
  }) : conversations = List.of(initialConversations),
       messages = Map.of(initialMessages);

  final List<ConversationSummary> conversations;
  final Map<String, List<ChatMessage>> messages;
  DashboardStats stats;
  int _newId = 1;
  String? failWith;
  final List<String> events = [];

  void _checkFailure() {
    if (failWith != null) {
      throw ConversationRepositoryException(failWith!);
    }
  }

  @override
  Future<List<ConversationSummary>> listConversations({
    String query = '',
    bool archived = false,
    bool favoritesOnly = false,
    int offset = 0,
    int pageSize = 30,
  }) async {
    _checkFailure();
    final normalized = query.toLowerCase();
    final filtered = conversations.where((conversation) {
      return conversation.isArchived == archived &&
          (!favoritesOnly || conversation.isFavorite) &&
          (normalized.isEmpty ||
              conversation.title.toLowerCase().contains(normalized) ||
              (conversation.lastMessage ?? '').toLowerCase().contains(
                normalized,
              ) ||
              (messages[conversation.id] ?? const <ChatMessage>[]).any(
                (message) => message.text.toLowerCase().contains(normalized),
              ));
    }).toList()..sort((a, b) => b.updatedAt.compareTo(a.updatedAt));
    return filtered.skip(offset).take(pageSize).toList();
  }

  @override
  Future<DashboardStats> loadStats() async {
    _checkFailure();
    return stats;
  }

  @override
  Future<ConversationSummary> createConversation() async {
    _checkFailure();
    final created = ConversationSummary(
      id: '00000000-0000-4000-8000-${_newId.toString().padLeft(12, '0')}',
      title: 'Nouvelle conversation',
      isArchived: false,
      isFavorite: false,
      createdAt: DateTime.now(),
      updatedAt: DateTime.now(),
      messageCount: 0,
    );
    _newId++;
    conversations.insert(0, created);
    events.add('create:${created.id}');
    return created;
  }

  @override
  Future<List<ChatMessage>> loadMessages(String conversationId) async {
    _checkFailure();
    events.add('load:$conversationId');
    return List.of(messages[conversationId] ?? const []);
  }

  @override
  Future<void> rename(String id, String title) async {
    _checkFailure();
    final index = conversations.indexWhere((item) => item.id == id);
    if (index < 0) throw const ConversationRepositoryException('missing');
    conversations[index] = _copy(conversations[index], title: title);
    events.add('rename:$id:$title');
  }

  @override
  Future<void> setArchived(String id, bool value) async {
    _checkFailure();
    final index = conversations.indexWhere((item) => item.id == id);
    if (index < 0) throw const ConversationRepositoryException('missing');
    conversations[index] = _copy(conversations[index], isArchived: value);
    events.add('archive:$id:$value');
  }

  @override
  Future<void> setFavorite(String id, bool value) async {
    _checkFailure();
    final index = conversations.indexWhere((item) => item.id == id);
    if (index < 0) throw const ConversationRepositoryException('missing');
    conversations[index] = _copy(conversations[index], isFavorite: value);
    events.add('favorite:$id:$value');
  }

  @override
  Future<void> delete(String id) async {
    _checkFailure();
    conversations.removeWhere((item) => item.id == id);
    messages.remove(id);
    events.add('delete:$id');
  }

  ConversationSummary _copy(
    ConversationSummary item, {
    String? title,
    bool? isArchived,
    bool? isFavorite,
  }) => ConversationSummary(
    id: item.id,
    title: title ?? item.title,
    isArchived: isArchived ?? item.isArchived,
    isFavorite: isFavorite ?? item.isFavorite,
    createdAt: item.createdAt,
    updatedAt: DateTime.now(),
    messageCount: item.messageCount,
    lastMessage: item.lastMessage,
  );
}

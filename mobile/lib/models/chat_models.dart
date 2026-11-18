class ChatSource {
  final String name;
  final String page;

  const ChatSource({required this.name, required this.page});

  factory ChatSource.fromJson(Map<String, dynamic> json) => ChatSource(
    name: (json['source'] ?? 'Document EMSI').toString(),
    page: (json['page'] ?? '?').toString(),
  );

  String get identity => '$name::$page';
}

class ChatMessage {
  final String text;
  final bool isUser;
  final DateTime createdAt;
  final List<ChatSource> sources;
  final List<String> images;
  final bool isError;
  final String? retryQuestion;

  ChatMessage({
    required this.text,
    required this.isUser,
    DateTime? createdAt,
    this.sources = const [],
    this.images = const [],
    this.isError = false,
    this.retryQuestion,
  }) : createdAt = createdAt ?? DateTime.now();
}

class ChatResponse {
  final String answer;
  final List<ChatSource> sources;
  final List<String> images;

  const ChatResponse({
    required this.answer,
    required this.sources,
    required this.images,
  });
}

class ConversationMemory {
  final List<Map<String, String>> _messages = [];
  static const int maxMessages = 10;
  static const int _maxMessageLength = 1000;

  List<Map<String, String>> get messages =>
      _messages.map((message) => Map<String, String>.from(message)).toList();

  void recordExchange(String question, String answer) {
    _messages
      ..add({'role': 'user', 'content': _bounded(question)})
      ..add({'role': 'assistant', 'content': _bounded(answer)});
    if (_messages.length > maxMessages) {
      _messages.removeRange(0, _messages.length - maxMessages);
    }
  }

  String _bounded(String value) => value.length <= _maxMessageLength
      ? value
      : value.substring(0, _maxMessageLength);

  void clear() => _messages.clear();
}

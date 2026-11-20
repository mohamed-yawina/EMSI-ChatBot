import 'chat_models.dart';

class ConversationSummary {
  const ConversationSummary({
    required this.id,
    required this.title,
    required this.isArchived,
    required this.isFavorite,
    required this.createdAt,
    required this.updatedAt,
    required this.messageCount,
    this.lastMessage,
  });

  final String id;
  final String title;
  final bool isArchived;
  final bool isFavorite;
  final DateTime createdAt;
  final DateTime updatedAt;
  final int messageCount;
  final String? lastMessage;

  factory ConversationSummary.fromJson(Map<String, dynamic> json) =>
      ConversationSummary(
        id: json['id'].toString(),
        title: json['title'].toString(),
        isArchived: json['is_archived'] == true,
        isFavorite: json['is_favorite'] == true,
        createdAt: DateTime.parse(json['created_at'].toString()).toLocal(),
        updatedAt: DateTime.parse(json['updated_at'].toString()).toLocal(),
        messageCount: int.tryParse(json['message_count'].toString()) ?? 0,
        lastMessage: json['last_message']?.toString(),
      );
}

class DashboardStats {
  const DashboardStats({
    required this.conversationCount,
    required this.messageCount,
    required this.favoriteCount,
    this.lastActivity,
  });

  final int conversationCount;
  final int messageCount;
  final int favoriteCount;
  final DateTime? lastActivity;

  factory DashboardStats.fromJson(Map<String, dynamic> json) => DashboardStats(
    conversationCount: int.tryParse(json['conversation_count'].toString()) ?? 0,
    messageCount: int.tryParse(json['message_count'].toString()) ?? 0,
    favoriteCount: int.tryParse(json['favorite_count'].toString()) ?? 0,
    lastActivity: json['last_activity'] == null
        ? null
        : DateTime.tryParse(json['last_activity'].toString())?.toLocal(),
  );
}

ChatMessage chatMessageFromStoredJson(
  Map<String, dynamic> json, {
  String? imageBaseUrl,
  String? trustedStorageBaseUrl,
}) {
  final sourceData = json['sources'];
  final sources = sourceData is List
      ? sourceData
            .whereType<Map<String, dynamic>>()
            .map(ChatSource.fromJson)
            .toList(growable: false)
      : const <ChatSource>[];
  final imageData = json['images'];
  final images = imageData is List
      ? imageData
            .map(
              (item) => ChatImage.fromJson(
                item,
                baseUrl: imageBaseUrl,
                trustedStorageBaseUrl: trustedStorageBaseUrl,
              ),
            )
            .where((image) => image.url.isNotEmpty)
            .toList(growable: false)
      : const <ChatImage>[];
  final timestamp = DateTime.tryParse(json['created_at'].toString());
  return ChatMessage(
    text: json['content'].toString(),
    isUser: json['role'] == 'user',
    createdAt: timestamp?.toLocal(),
    sources: sources,
    images: images,
  );
}

import 'package:flutter/foundation.dart';

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

class ChatImage {
  final String url;
  final String? source;
  final String? page;
  final String? caption;
  final bool captionVerified;
  final String? context;
  final Uint8List? bytes;
  final String? mimeType;
  final String? storagePath;

  const ChatImage({
    required this.url,
    this.source,
    this.page,
    this.caption,
    this.captionVerified = false,
    this.context,
    this.bytes,
    this.mimeType,
    this.storagePath,
  });

  String get displayLabel {
    if (bytes != null || storagePath != null) {
      return 'Image jointe à la conversation';
    }
    final verifiedCaption = caption?.trim();
    if (captionVerified &&
        verifiedCaption != null &&
        verifiedCaption.isNotEmpty) {
      return verifiedCaption;
    }
    final pageNumber = page?.trim();
    if (pageNumber != null && pageNumber.isNotEmpty) {
      return 'Visuel de la brochure EMSI — page $pageNumber';
    }
    return 'Visuel de la brochure EMSI';
  }

  factory ChatImage.fromJson(
    dynamic value, {
    String? baseUrl,
    String? trustedStorageBaseUrl,
  }) {
    final map = value is Map ? value : const <String, dynamic>{};
    final rawUrl = value is String ? value : map['url']?.toString() ?? '';
    final apiUrl = resolveApiImageUrl(rawUrl, baseUrl: baseUrl);
    return ChatImage(
      url: apiUrl.isNotEmpty
          ? apiUrl
          : _resolveSignedStorageUrl(rawUrl, trustedStorageBaseUrl),
      source: map['source']?.toString(),
      page: map['page']?.toString(),
      caption: map['caption_verified'] == true
          ? map['caption']?.toString()
          : null,
      captionVerified: map['caption_verified'] == true,
      context: map['context']?.toString(),
      mimeType: map['mime_type']?.toString(),
      storagePath: map['storage_path']?.toString(),
    );
  }
}

String _resolveSignedStorageUrl(String rawUrl, String? trustedBaseUrl) {
  if (trustedBaseUrl == null || rawUrl.isEmpty) return '';
  final expected = Uri.tryParse(trustedBaseUrl);
  final candidate = Uri.tryParse(rawUrl);
  if (expected == null ||
      candidate == null ||
      expected.scheme != 'https' ||
      candidate.scheme != 'https' ||
      expected.host != candidate.host ||
      expected.port != candidate.port ||
      candidate.userInfo.isNotEmpty ||
      candidate.hasFragment ||
      !candidate.path.startsWith('/storage/v1/object/sign/chat-uploads/')) {
    return '';
  }
  return candidate.toString();
}

String resolveApiImageUrl(String path, {String? baseUrl}) {
  final configured = (baseUrl ?? const String.fromEnvironment('API_BASE_URL'))
      .trim();
  final defaultBase = kIsWeb
      ? 'http://127.0.0.1:8000'
      : defaultTargetPlatform == TargetPlatform.android
      ? 'http://10.0.2.2:8000'
      : 'http://127.0.0.1:8000';
  final base = Uri.parse(
    (configured.isEmpty ? defaultBase : configured).replaceFirst(
      RegExp(r'/$'),
      '',
    ),
  );
  final parsed = Uri.tryParse(path.trim());
  if (parsed == null || !parsed.hasAuthority && path.trim().isEmpty) return '';
  if (parsed.userInfo.isNotEmpty || parsed.hasFragment) return '';
  if (parsed.pathSegments.any((segment) => segment == '..')) return '';
  final resolved = parsed.hasScheme ? parsed : base.resolveUri(parsed);
  if ((resolved.scheme != 'http' && resolved.scheme != 'https') ||
      resolved.scheme != base.scheme ||
      resolved.host != base.host ||
      resolved.port != base.port ||
      !resolved.path.startsWith('/images/')) {
    return '';
  }
  return resolved.toString();
}

class ChatMessage {
  final String text;
  final bool isUser;
  final DateTime createdAt;
  final List<ChatSource> sources;
  final List<ChatImage> images;
  final bool isError;
  final String? retryQuestion;
  final String? retryRequestId;
  final Uint8List? retryImageBytes;
  final String? retryImageMimeType;

  ChatMessage({
    required this.text,
    required this.isUser,
    DateTime? createdAt,
    this.sources = const [],
    this.images = const [],
    this.isError = false,
    this.retryQuestion,
    this.retryRequestId,
    this.retryImageBytes,
    this.retryImageMimeType,
  }) : createdAt = createdAt ?? DateTime.now();
}

class ChatResponse {
  final String answer;
  final List<ChatSource> sources;
  final List<ChatImage> images;

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

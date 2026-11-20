import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../models/chat_models.dart';
import 'image_selection_service.dart';

class ChatRequestException implements Exception {
  final String message;
  const ChatRequestException(this.message);

  @override
  String toString() => message;
}

class ChatApiService {
  ChatApiService({http.Client? client, String? baseUrl})
    : _client = client ?? http.Client(),
      _ownsClient = client == null,
      _baseUrl = _normalizeBaseUrl(baseUrl ?? _configuredBaseUrl);

  final http.Client _client;
  final bool _ownsClient;
  final String _baseUrl;

  static const String _configuredBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
  );

  static String get defaultBaseUrl {
    if (kIsWeb) return 'http://127.0.0.1:8000';
    if (defaultTargetPlatform == TargetPlatform.android) {
      return 'http://10.0.2.2:8000';
    }
    return 'http://127.0.0.1:8000';
  }

  String get baseUrl => _baseUrl;

  static String _normalizeBaseUrl(String value) {
    final chosen = value.trim().isEmpty ? defaultBaseUrl : value.trim();
    return chosen.endsWith('/')
        ? chosen.substring(0, chosen.length - 1)
        : chosen;
  }

  Future<ChatResponse> sendQuestion({
    required String question,
    required List<Map<String, String>> history,
    required bool includeImages,
    String? conversationId,
    String? accessToken,
    String? requestId,
    SelectedChatImage? attachment,
  }) async {
    final persistent = conversationId != null;
    if (persistent &&
        (accessToken == null || accessToken.isEmpty || requestId == null)) {
      throw const ChatRequestException(
        'Votre session a expiré. Reconnectez-vous pour continuer.',
      );
    }
    if (attachment != null && !persistent) {
      throw const ChatRequestException(
        'Connectez-vous pour envoyer une image au chatbot.',
      );
    }
    final payload = <String, dynamic>{
      'question': question,
      'use_llm': true,
      'include_images': includeImages,
    };
    if (persistent) {
      payload['request_id'] = requestId;
    } else {
      payload['history'] = history;
    }
    final endpoint = persistent
        ? '$_baseUrl/api/conversations/$conversationId/${attachment == null ? 'chat' : 'vision'}'
        : '$_baseUrl/api/chat';
    final headers = <String, String>{
      'Content-Type': 'application/json; charset=utf-8',
      if (persistent) 'Authorization': 'Bearer $accessToken',
    };
    late final http.Response response;
    try {
      if (attachment == null) {
        response = await _client
            .post(
              Uri.parse(endpoint),
              headers: headers,
              body: jsonEncode(payload),
            )
            .timeout(const Duration(seconds: 240));
      } else {
        final multipart = http.MultipartRequest('POST', Uri.parse(endpoint))
          ..headers['Authorization'] = 'Bearer $accessToken'
          ..fields['question'] = question
          ..fields['request_id'] = requestId!;
        multipart.files.add(
          http.MultipartFile.fromBytes(
            'image',
            attachment.bytes,
            filename: 'upload',
          ),
        );
        final streamed = await _client
            .send(multipart)
            .timeout(const Duration(seconds: 90));
        response = await http.Response.fromStream(streamed)
            .timeout(const Duration(seconds: 30));
      }
    } on TimeoutException {
      throw const ChatRequestException(
        'La réponse prend trop de temps. Vérifiez que FastAPI fonctionne puis réessayez.',
      );
    } on http.ClientException {
      throw const ChatRequestException(
        'Connexion au serveur impossible. Vérifiez l’adresse FastAPI et réessayez.',
      );
    }

    if (response.statusCode != 200) {
      throw ChatRequestException(_messageForStatus(response.statusCode));
    }

    final dynamic decoded;
    try {
      decoded = jsonDecode(utf8.decode(response.bodyBytes));
    } on FormatException {
      throw const ChatRequestException(
        'Le serveur a retourné une réponse illisible. Réessayez dans un instant.',
      );
    }
    if (decoded is! Map<String, dynamic>) {
      throw const ChatRequestException(
        'Le serveur a retourné une réponse inattendue.',
      );
    }

    final rawSources = decoded['sources'];
    final sources = <ChatSource>[];
    final seenSources = <String>{};
    if (rawSources is List) {
      for (final raw in rawSources.whereType<Map<String, dynamic>>()) {
        final source = ChatSource.fromJson(raw);
        if (seenSources.add(source.identity)) sources.add(source);
      }
    }

    final images = <ChatImage>[];
    final rawImages = decoded['images'];
    if (rawImages is List) {
      for (final item in rawImages) {
        final image = ChatImage.fromJson(item, baseUrl: _baseUrl);
        final resolved = image.url;
        if (resolved.isNotEmpty &&
            !images.any((saved) => saved.url == resolved)) {
          images.add(
            ChatImage(
              url: resolved,
              source: image.source,
              page: image.page,
              caption: image.caption,
              context: image.context,
            ),
          );
        }
      }
    }

    return ChatResponse(
      answer: (decoded['answer'] ?? 'Aucune réponse disponible.').toString(),
      sources: sources,
      images: images,
    );
  }

  String _messageForStatus(int statusCode) => switch (statusCode) {
    401 => 'Votre session a expiré. Reconnectez-vous puis réessayez.',
    403 ||
    404 => 'Cette conversation n’est plus accessible. Actualisez l’historique.',
    422 =>
      'La question ne peut pas être traitée. Reformulez-la puis réessayez.',
    413 => 'L\u2019image d\u00e9passe la limite de 5 Mo.',
    415 => 'Utilisez une image JPEG, PNG ou WebP.',
    429 || 503 =>
      'Le service est occupé pour le moment. Réessayez dans quelques instants.',
    500 || 502 =>
      'Le serveur a rencontré un problème. Réessayez dans quelques instants.',
    504 =>
      'Le serveur met trop de temps à répondre. Réessayez dans un instant.',
    _ => 'Le serveur est temporairement indisponible (erreur $statusCode).',
  };

  void dispose() {
    if (_ownsClient) _client.close();
  }
}

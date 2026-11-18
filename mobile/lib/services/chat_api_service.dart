import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../models/chat_models.dart';

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
  }) async {
    late final http.Response response;
    try {
      response = await _client
          .post(
            Uri.parse('$_baseUrl/api/chat'),
            headers: const {'Content-Type': 'application/json; charset=utf-8'},
            body: jsonEncode({
              'question': question,
              'use_llm': true,
              'include_images': includeImages,
              'history': history,
            }),
          )
          .timeout(const Duration(seconds: 240));
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

    final images = <String>[];
    final rawImages = decoded['images'];
    if (rawImages is List) {
      for (final item in rawImages) {
        final path = item is String
            ? item
            : item is Map
            ? item['url']?.toString()
            : null;
        if (path == null || path.isEmpty) continue;
        final uri = Uri.tryParse(path);
        if (uri == null) continue;
        final baseUri = Uri.parse(_baseUrl);
        final imageUri = uri.hasScheme ? uri : baseUri.resolveUri(uri);
        if ((imageUri.scheme == 'http' || imageUri.scheme == 'https') &&
            imageUri.scheme == baseUri.scheme &&
            imageUri.host == baseUri.host &&
            imageUri.port == baseUri.port &&
            !images.contains(imageUri.toString())) {
          images.add(imageUri.toString());
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
    422 =>
      'La question ne peut pas être traitée. Reformulez-la puis réessayez.',
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

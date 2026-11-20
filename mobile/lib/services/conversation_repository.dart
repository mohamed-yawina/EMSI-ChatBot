import 'package:supabase_flutter/supabase_flutter.dart';

import '../app/supabase_config.dart';
import '../models/chat_models.dart';
import '../models/conversation_models.dart';

class ConversationRepositoryException implements Exception {
  const ConversationRepositoryException(this.message);
  final String message;

  @override
  String toString() => message;
}

class ConversationCleanupException extends ConversationRepositoryException {
  const ConversationCleanupException(super.message);
}

/// PostgREST OR filter for case-insensitive title or full message-content search.
String buildConversationSearchFilter(String query) {
  final escaped = query
      .trim()
      .replaceAll('\\', '\\\\')
      .replaceAll('"', '\\"')
      .replaceAll('%', r'\%')
      .replaceAll('_', r'\_');
  final pattern = '"%$escaped%"';
  return 'title.ilike.$pattern,search_text.ilike.$pattern';
}

bool _isOwnedUploadPath(String path, String userId) {
  final parts = path.split('/');
  final uuid = RegExp(
    r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$',
  );
  if (parts.length != 3 || parts[0] != userId || !uuid.hasMatch(parts[1])) {
    return false;
  }
  return RegExp(
    r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\.(jpg|png|webp)$',
    caseSensitive: false,
  ).hasMatch(parts[2]);
}

abstract interface class ConversationRepository {
  Future<List<ConversationSummary>> listConversations({
    String query,
    bool archived,
    bool favoritesOnly,
    int offset,
    int pageSize,
  });
  Future<DashboardStats> loadStats();
  Future<ConversationSummary> createConversation();
  Future<List<ChatMessage>> loadMessages(String conversationId);
  Future<void> rename(String id, String title);
  Future<void> setArchived(String id, bool value);
  Future<void> setFavorite(String id, bool value);
  Future<void> delete(String id);
}

class SupabaseConversationRepository implements ConversationRepository {
  SupabaseConversationRepository(this._client, {this.imageBaseUrl});
  final SupabaseClient _client;
  final String? imageBaseUrl;

  String get _userId {
    final id = _client.auth.currentUser?.id;
    if (id == null) {
      throw const ConversationRepositoryException(
        'Votre session a expiré. Reconnectez-vous.',
      );
    }
    return id;
  }

  @override
  Future<List<ConversationSummary>> listConversations({
    String query = '',
    bool archived = false,
    bool favoritesOnly = false,
    int offset = 0,
    int pageSize = 30,
  }) async {
    try {
      var request = _client
          .from('conversation_summaries')
          .select(
            'id,user_id,title,is_archived,is_favorite,created_at,updated_at,message_count,last_message',
          )
          .eq('user_id', _userId)
          .eq('is_archived', archived);
      if (favoritesOnly) request = request.eq('is_favorite', true);
      if (query.trim().isNotEmpty) {
        request = request.or(buildConversationSearchFilter(query));
      }
      final rows = await request
          .order('updated_at', ascending: false)
          .order('id', ascending: false)
          .range(offset, offset + pageSize - 1);
      return rows
          .map((row) => ConversationSummary.fromJson(row))
          .toList(growable: false);
    } on ConversationRepositoryException {
      rethrow;
    } catch (_) {
      throw const ConversationRepositoryException(
        'Impossible de charger vos conversations. Vérifiez votre connexion.',
      );
    }
  }

  @override
  Future<DashboardStats> loadStats() async {
    try {
      final result = await _client.rpc('get_my_dashboard_stats');
      if (result is List && result.isNotEmpty && result.first is Map) {
        return DashboardStats.fromJson(
          Map<String, dynamic>.from(result.first as Map),
        );
      }
      return const DashboardStats(
        conversationCount: 0,
        messageCount: 0,
        favoriteCount: 0,
      );
    } catch (_) {
      throw const ConversationRepositoryException(
        'Impossible de charger les statistiques de votre compte.',
      );
    }
  }

  @override
  Future<ConversationSummary> createConversation() async {
    try {
      final row = await _client
          .from('conversations')
          .insert({'user_id': _userId, 'title': 'Nouvelle conversation'})
          .select(
            'id,user_id,title,is_archived,is_favorite,created_at,updated_at',
          )
          .single();
      return ConversationSummary.fromJson({...row, 'message_count': 0});
    } catch (_) {
      throw const ConversationRepositoryException(
        'Impossible de créer la conversation. Réessayez.',
      );
    }
  }

  @override
  Future<List<ChatMessage>> loadMessages(String conversationId) async {
    try {
      final rows = await _client
          .from('messages')
          .select('role,content,sources,images,created_at,sequence_number')
          .eq('conversation_id', conversationId)
          .eq('user_id', _userId)
          .order('sequence_number', ascending: true);
      final messages = <ChatMessage>[];
      for (final rawRow in rows) {
        final row = Map<String, dynamic>.from(rawRow);
        final rawImages = row['images'];
        if (rawImages is List) {
          final signedImages = <Map<String, dynamic>>[];
          for (final rawImage in rawImages.whereType<Map>()) {
            final image = Map<String, dynamic>.from(rawImage);
            final path = image['storage_path']?.toString() ?? '';
            if (image['bucket'] == 'chat-uploads' &&
                _isOwnedUploadPath(path, _userId)) {
              try {
                image['url'] = await _client.storage
                    .from('chat-uploads')
                    .createSignedUrl(path, 3600);
              } catch (_) {
                // Keep the message history readable if one private object is gone.
                image['url'] = '';
              }
            }
            signedImages.add(image);
          }
          row['images'] = signedImages;
        }
        messages.add(
          chatMessageFromStoredJson(
            row,
            imageBaseUrl: imageBaseUrl,
            trustedStorageBaseUrl: SupabaseConfig.url,
          ),
        );
      }
      return messages;
    } catch (_) {
      throw const ConversationRepositoryException(
        'Impossible de charger les messages de cette conversation.',
      );
    }
  }

  @override
  Future<void> rename(String id, String title) => _update(id, {
    'title': title.trim(),
  }, 'Impossible de renommer la conversation.');

  @override
  Future<void> setArchived(String id, bool value) => _update(id, {
    'is_archived': value,
  }, 'Impossible de modifier l’archivage.');

  @override
  Future<void> setFavorite(String id, bool value) => _update(id, {
    'is_favorite': value,
  }, 'Impossible de modifier les favoris.');

  @override
  Future<void> delete(String id) async {
    try {
      final rows = await _client
          .from('messages')
          .select('images')
          .eq('conversation_id', id)
          .eq('user_id', _userId);
      final imagePaths = <String>[];
      for (final row in rows) {
        final images = row['images'];
        if (images is List) {
          for (final value in images.whereType<Map>()) {
            final path = value['storage_path']?.toString() ?? '';
            if (value['bucket'] == 'chat-uploads' &&
                _isOwnedUploadPath(path, _userId)) {
              imagePaths.add(path);
            }
          }
        }
      }
      final deleted = await _client
          .from('conversations')
          .delete()
          .eq('id', id)
          .eq('user_id', _userId)
          .select('id')
          .maybeSingle();
      if (deleted == null) {
        throw const ConversationRepositoryException(
          'La conversation a déjà été supprimée ou n’est plus accessible.',
        );
      }
      if (imagePaths.isNotEmpty) {
        try {
          await _client.storage.from('chat-uploads').remove(imagePaths);
        } catch (_) {
          throw const ConversationCleanupException(
            'La conversation est supprimée, mais certaines images privées restent à nettoyer.',
          );
        }
      }
    } on ConversationRepositoryException {
      rethrow;
    } catch (_) {
      throw const ConversationRepositoryException(
        'Impossible de supprimer la conversation.',
      );
    }
  }

  Future<void> _update(
    String id,
    Map<String, dynamic> values,
    String errorMessage,
  ) async {
    try {
      final updated = await _client
          .from('conversations')
          .update(values)
          .eq('id', id)
          .eq('user_id', _userId)
          .select('id')
          .maybeSingle();
      if (updated == null) {
        throw const ConversationRepositoryException(
          'La conversation a déjà changé ou n’est plus accessible.',
        );
      }
    } on ConversationRepositoryException {
      rethrow;
    } catch (_) {
      throw ConversationRepositoryException(errorMessage);
    }
  }
}

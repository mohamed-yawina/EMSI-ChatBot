import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/chat_models.dart';
import 'markdown_content.dart';

class ChatMessageBubble extends StatelessWidget {
  const ChatMessageBubble({super.key, required this.message, this.onRetry});

  final ChatMessage message;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;
    final isUser = message.isUser;
    final isError = message.isError;
    final background = isUser
        ? colors.primaryContainer
        : (isError ? colors.errorContainer : colors.surface);
    final foreground = isError ? colors.onErrorContainer : colors.onSurface;

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 10),
      child: Row(
        mainAxisAlignment: isUser
            ? MainAxisAlignment.end
            : MainAxisAlignment.start,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (!isUser) ...[
            CircleAvatar(
              radius: 17,
              backgroundColor: isError ? colors.error : colors.primary,
              child: Icon(
                isError ? Icons.info_outline_rounded : Icons.school_rounded,
                color: isError ? colors.onError : colors.onPrimary,
                size: 18,
              ),
            ),
            const SizedBox(width: 10),
          ],
          Flexible(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 760),
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: background,
                  borderRadius: BorderRadius.only(
                    topLeft: const Radius.circular(20),
                    topRight: const Radius.circular(20),
                    bottomLeft: Radius.circular(isUser ? 20 : 5),
                    bottomRight: Radius.circular(isUser ? 5 : 20),
                  ),
                  border: Border.all(
                    color: isUser
                        ? colors.primary.withValues(alpha: 0.14)
                        : colors.outlineVariant,
                  ),
                ),
                child: Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 18,
                    vertical: 15,
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if (!isUser)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 7),
                          child: Text(
                            isError ? 'Connexion' : 'EMSI-ChatBot',
                            style: theme.textTheme.labelMedium?.copyWith(
                              color: isError ? colors.error : colors.primary,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ),
                      MarkdownContent(data: message.text, color: foreground),
                      if (message.images.isNotEmpty) ...[
                        const SizedBox(height: 14),
                        ImageGallery(images: message.images),
                      ],
                      if (message.sources.isNotEmpty) ...[
                        const SizedBox(height: 15),
                        SourceReferences(sources: message.sources),
                      ],
                      if (!isUser) ...[
                        const SizedBox(height: 9),
                        Wrap(
                          crossAxisAlignment: WrapCrossAlignment.center,
                          spacing: 8,
                          children: [
                            Text(
                              _formatTime(message.createdAt),
                              style: theme.textTheme.labelSmall?.copyWith(
                                color: colors.onSurfaceVariant,
                              ),
                            ),
                            IconButton(
                              tooltip: 'Copier la réponse',
                              visualDensity: VisualDensity.compact,
                              onPressed: isError
                                  ? null
                                  : () => _copy(context, message.text),
                              icon: const Icon(
                                Icons.content_copy_rounded,
                                size: 16,
                              ),
                            ),
                            if (isError && onRetry != null) ...[
                              TextButton.icon(
                                onPressed: onRetry,
                                icon: const Icon(
                                  Icons.refresh_rounded,
                                  size: 17,
                                ),
                                label: const Text('Réessayer'),
                              ),
                            ],
                          ],
                        ),
                      ],
                    ],
                  ),
                ),
              ),
            ),
          ),
          if (isUser) ...[
            const SizedBox(width: 10),
            CircleAvatar(
              radius: 17,
              backgroundColor: colors.secondaryContainer,
              child: Icon(
                Icons.person_outline_rounded,
                color: colors.onSecondaryContainer,
                size: 18,
              ),
            ),
          ],
        ],
      ),
    );
  }

  Future<void> _copy(BuildContext context, String text) async {
    await Clipboard.setData(ClipboardData(text: text));
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Réponse copiée dans le presse-papiers.')),
    );
  }

  String _formatTime(DateTime time) =>
      '${time.hour.toString().padLeft(2, '0')}:${time.minute.toString().padLeft(2, '0')}';
}

class SourceReferences extends StatelessWidget {
  const SourceReferences({super.key, required this.sources});

  final List<ChatSource> sources;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final unique = <String, ChatSource>{
      for (final source in sources) source.identity: source,
    }.values;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.only(top: 11),
      decoration: BoxDecoration(
        border: Border(
          top: BorderSide(color: theme.colorScheme.outlineVariant),
        ),
      ),
      child: Wrap(
        spacing: 7,
        runSpacing: 7,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          Text(
            'Sources',
            style: theme.textTheme.labelMedium?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
              fontWeight: FontWeight.w700,
            ),
          ),
          for (final source in unique)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color: theme.colorScheme.surfaceContainerLow,
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: theme.colorScheme.outlineVariant),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    Icons.description_outlined,
                    size: 15,
                    color: theme.colorScheme.primary,
                  ),
                  const SizedBox(width: 6),
                  ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 250),
                    child: Text(
                      '${source.name} · page ${source.page}',
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.labelSmall,
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class ImageGallery extends StatefulWidget {
  const ImageGallery({super.key, required this.images});

  final List<ChatImage> images;

  @override
  State<ImageGallery> createState() => _ImageGalleryState();
}

class _ImageGalleryState extends State<ImageGallery> {
  final Set<String> _failed = {};

  @override
  Widget build(BuildContext context) {
    final available = widget.images
        .where((image) => !_failed.contains(image.url))
        .toList();
    if (available.isEmpty) {
      return Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surfaceContainerLow,
          borderRadius: BorderRadius.circular(12),
        ),
        child: const Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.image_not_supported_outlined, size: 18),
            SizedBox(width: 8),
            Flexible(
              child: Text(
                'Les images de la brochure ne sont pas accessibles pour le moment.',
              ),
            ),
          ],
        ),
      );
    }
    return SizedBox(
      height: 184,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: available.length,
        separatorBuilder: (_, _) => const SizedBox(width: 10),
        itemBuilder: (context, index) {
          final image = available[index];
          return SizedBox(
            width: 195,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(14),
                    child: image.bytes != null
                        ? Image.memory(
                            image.bytes!,
                            width: 195,
                            fit: BoxFit.cover,
                            errorBuilder: (context, error, stackTrace) =>
                                const Icon(Icons.broken_image_outlined),
                          )
                        : Image.network(
                            image.url,
                            width: 195,
                            fit: BoxFit.cover,
                            errorBuilder: (context, error, stackTrace) {
                              WidgetsBinding.instance.addPostFrameCallback((_) {
                                if (mounted) {
                                  setState(() => _failed.add(image.url));
                                }
                              });
                              return const SizedBox.shrink();
                            },
                          ),
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  image.displayLabel,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.labelSmall,
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}

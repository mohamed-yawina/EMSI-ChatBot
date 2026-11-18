import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

class MarkdownContent extends StatefulWidget {
  const MarkdownContent({super.key, required this.data, this.color});

  final String data;
  final Color? color;

  @override
  State<MarkdownContent> createState() => _MarkdownContentState();
}

class _MarkdownContentState extends State<MarkdownContent> {
  final List<TapGestureRecognizer> _recognizers = [];
  final RegExp _inlinePattern = RegExp(
    r'\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)|\*\*([^*]+)\*\*',
  );

  @override
  void dispose() {
    _disposeRecognizers();
    super.dispose();
  }

  void _disposeRecognizers() {
    for (final recognizer in _recognizers) {
      recognizer.dispose();
    }
    _recognizers.clear();
  }

  Future<void> _openLink(Uri uri) async {
    try {
      final opened = await launchUrl(uri, mode: LaunchMode.platformDefault);
      if (!opened && mounted) _showLinkError();
    } catch (_) {
      if (mounted) _showLinkError();
    }
  }

  void _showLinkError() {
    ScaffoldMessenger.maybeOf(context)?.showSnackBar(
      const SnackBar(content: Text("Impossible d'ouvrir ce lien.")),
    );
  }

  List<InlineSpan> _inlineSpans(String text, TextStyle baseStyle) {
    final spans = <InlineSpan>[];
    var cursor = 0;
    for (final match in _inlinePattern.allMatches(text)) {
      if (match.start > cursor) {
        spans.add(TextSpan(text: text.substring(cursor, match.start)));
      }
      final label = match.group(1);
      final rawUrl = match.group(2);
      final boldText = match.group(3);
      if (label != null && rawUrl != null) {
        final normalizedUrl = rawUrl.replaceFirst(RegExp(r'[.,!?;:]$'), '');
        final uri = Uri.tryParse(normalizedUrl);
        if (uri != null &&
            (uri.scheme == 'http' || uri.scheme == 'https') &&
            uri.host.isNotEmpty &&
            uri.userInfo.isEmpty) {
          final recognizer = TapGestureRecognizer()
            ..onTap = () => _openLink(uri);
          _recognizers.add(recognizer);
          spans.add(
            TextSpan(
              text: label,
              style: baseStyle.copyWith(
                color: Theme.of(context).colorScheme.primary,
                decoration: TextDecoration.underline,
              ),
              recognizer: recognizer,
            ),
          );
          final punctuation = rawUrl.substring(normalizedUrl.length);
          if (punctuation.isNotEmpty) spans.add(TextSpan(text: punctuation));
        } else {
          spans.add(TextSpan(text: label));
        }
      } else if (boldText != null) {
        spans.add(
          TextSpan(
            text: boldText,
            style: baseStyle.copyWith(fontWeight: FontWeight.w700),
          ),
        );
      }
      cursor = match.end;
    }
    if (cursor < text.length) spans.add(TextSpan(text: text.substring(cursor)));
    return spans;
  }

  Widget _richLine(String text, TextStyle style) => Text.rich(
    TextSpan(style: style, children: _inlineSpans(text, style)),
    softWrap: true,
  );

  @override
  Widget build(BuildContext context) {
    _disposeRecognizers();
    final theme = Theme.of(context);
    final bodyStyle =
        theme.textTheme.bodyLarge?.copyWith(
          color: widget.color ?? theme.colorScheme.onSurface,
          height: 1.58,
        ) ??
        TextStyle(
          color: widget.color ?? theme.colorScheme.onSurface,
          fontSize: 15,
          height: 1.58,
        );
    final lines = widget.data.replaceAll('\r\n', '\n').split('\n');
    final blocks = <Widget>[];
    final paragraph = <String>[];

    void flushParagraph() {
      if (paragraph.isEmpty) return;
      blocks.add(_richLine(paragraph.join(' '), bodyStyle));
      blocks.add(const SizedBox(height: 10));
      paragraph.clear();
    }

    for (final rawLine in lines) {
      final line = rawLine.trimRight();
      if (line.trim().isEmpty) {
        flushParagraph();
        continue;
      }
      final heading = RegExp(r'^(#{1,3})\s+(.+)$').firstMatch(line.trimLeft());
      if (heading != null) {
        flushParagraph();
        final level = heading.group(1)!.length;
        final size = level == 1 ? 21.0 : (level == 2 ? 18.0 : 16.0);
        blocks.add(
          Padding(
            padding: const EdgeInsets.only(top: 8, bottom: 6),
            child: _richLine(
              heading.group(2)!,
              bodyStyle.copyWith(
                fontSize: size,
                height: 1.3,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        );
        continue;
      }
      final bullet = RegExp(r'^\s*[-*]\s+(.+)$').firstMatch(line);
      final numbered = RegExp(r'^\s*\d+[.)]\s+(.+)$').firstMatch(line);
      if (bullet != null || numbered != null) {
        flushParagraph();
        final content = (bullet ?? numbered)!.group(1)!;
        blocks.add(
          Padding(
            padding: const EdgeInsets.only(left: 4, top: 3, bottom: 3),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Padding(
                  padding: const EdgeInsets.only(top: 8, right: 10),
                  child: Icon(
                    Icons.circle,
                    size: 6,
                    color: theme.colorScheme.secondary,
                  ),
                ),
                Expanded(child: _richLine(content, bodyStyle)),
              ],
            ),
          ),
        );
        continue;
      }
      paragraph.add(line.trim());
    }
    flushParagraph();
    if (blocks.isNotEmpty && blocks.last is SizedBox) blocks.removeLast();
    return SelectionArea(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: blocks,
      ),
    );
  }
}

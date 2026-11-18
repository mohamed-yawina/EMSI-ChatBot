import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:emsi_chatbot/main.dart';
import 'package:emsi_chatbot/widgets/markdown_content.dart';

void main() {
  testWidgets('shows the welcome screen and sends a real suggestion request', (
    tester,
  ) async {
    Map<String, dynamic>? requestBody;
    final client = MockClient((request) async {
      requestBody = jsonDecode(request.body) as Map<String, dynamic>;
      return http.Response(
        jsonEncode({
          'answer': 'Les campus cités sont Rabat et Casablanca [[REF:A]].',
          'sources': [
            {'source': 'Brochure-EMSI.pdf', 'page': 4},
            {'source': 'Brochure-EMSI.pdf', 'page': 4},
          ],
          'images': [],
        }),
        200,
        headers: {'content-type': 'application/json; charset=utf-8'},
      );
    });

    await tester.pumpWidget(MaterialApp(home: ChatScreen(client: client)));
    await tester.pumpAndSettle();

    expect(
      find.textContaining('Bonjour, que souhaitez-vous découvrir ?'),
      findsOneWidget,
    );
    expect(find.text('Quelles sont les filières proposées ?'), findsOneWidget);
    await tester.tap(find.text('Quels sont les campus EMSI ?'));
    await tester.pumpAndSettle();

    expect(requestBody!['question'], 'Quels sont les campus EMSI ?');
    expect(requestBody!['use_llm'], isTrue);
    expect(requestBody!['include_images'], isFalse);
    expect(requestBody!['history'], isEmpty);
    expect(find.textContaining('Rabat et Casablanca'), findsOneWidget);
    expect(find.text('Brochure-EMSI.pdf · page 4'), findsOneWidget);
  });

  testWidgets('renders Markdown headings, lists, bold and safe links', (
    tester,
  ) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: MarkdownContent(
            data: '# Campus EMSI\nRabat **accueille** les étudiants.\n- Campus de Rabat\n[Brochure](https://emsi.ma/brochure)',
          ),
        ),
      ),
    );

    expect(find.text('Campus EMSI'), findsOneWidget);
    expect(find.textContaining('accueille'), findsOneWidget);
    expect(find.text('Campus de Rabat'), findsOneWidget);
    expect(find.text('Brochure'), findsOneWidget);
  });

  test('maps source metadata and deduplicates by document and page', () {
    final source = ChatSource.fromJson({
      'source': 'Brochure-EMSI.pdf',
      'page': 4,
    });
    expect(source.name, 'Brochure-EMSI.pdf');
    expect(source.page, '4');
    expect(source.identity, 'Brochure-EMSI.pdf::4');
  });

  test('conversation memory keeps five exchanges, is isolated, and clears', () {
    final first = ConversationMemory();
    final second = ConversationMemory();
    for (var index = 0; index < 7; index++) {
      first.recordExchange('Question $index', 'Réponse $index');
    }

    expect(first.messages, hasLength(10));
    expect(first.messages.first['content'], 'Question 2');
    expect(first.messages.last['content'], 'Réponse 6');
    expect(second.messages, isEmpty);

    first.clear();
    expect(first.messages, isEmpty);
  });

  testWidgets(
    'resets conversation history and sends images only when enabled',
    (tester) async {
      final requestBodies = <Map<String, dynamic>>[];
      final client = MockClient((request) async {
        requestBodies.add(jsonDecode(request.body) as Map<String, dynamic>);
        return http.Response(
          jsonEncode({'answer': 'Réponse EMSI', 'sources': [], 'images': []}),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      });
      await tester.pumpWidget(
        MaterialApp(
          home: ChatScreen(client: client, apiBaseUrl: 'http://127.0.0.1:8000'),
        ),
      );
      await tester.pumpAndSettle();

      Future<void> send(String question) async {
        await tester.enterText(find.byType(TextField), question);
        await tester.tap(find.byTooltip('Envoyer'));
        await tester.pump();
        await tester.pumpAndSettle();
      }

      await tester.tap(find.byType(FilterChip));
      await tester.pumpAndSettle();
      await send('Question 1');
      await send('Question 2');
      expect(requestBodies[0]['include_images'], isTrue);
      final secondHistory = requestBodies[1]['history'] as List<dynamic>;
      expect(secondHistory, hasLength(2));
      expect(secondHistory.first['content'], 'Question 1');

      await tester.tap(find.byTooltip('Nouvelle conversation'));
      await tester.pumpAndSettle();
      await send('Nouvelle question');
      expect(requestBodies.last['history'], isEmpty);
      expect(requestBodies.last['include_images'], isTrue);
      expect(find.text('Question 1'), findsNothing);
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );

  testWidgets('shows sources and image results returned by FastAPI', (
    tester,
  ) async {
    final client = MockClient(
      (_) async => http.Response(
        jsonEncode({
          'answer': 'Réponse documentée.',
          'sources': [
            {'source': 'Brochure-EMSI.pdf', 'page': 8},
          ],
          'images': [
            {'url': '/images/campus-rabat.jpg'},
          ],
        }),
        200,
        headers: {'content-type': 'application/json; charset=utf-8'},
      ),
    );
    await tester.pumpWidget(
      MaterialApp(
        home: ChatScreen(client: client, apiBaseUrl: 'http://127.0.0.1:8000'),
      ),
    );
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byType(TextField),
      'Montre les images du campus',
    );
    await tester.tap(find.byTooltip('Envoyer'));
    await tester.pump();
    await tester.pumpAndSettle();

    expect(find.text('Brochure-EMSI.pdf · page 8'), findsOneWidget);
    expect(find.byType(ImageGallery), findsOneWidget);
    expect(find.text('Image indisponible'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('shows a clear network error with a working retry action', (
    tester,
  ) async {
    var calls = 0;
    final client = MockClient((request) async {
      calls++;
      if (calls == 1) throw http.ClientException('simulated offline');
      return http.Response(
        jsonEncode({
          'answer': 'Connexion rétablie.',
          'sources': [],
          'images': [],
        }),
        200,
        headers: {'content-type': 'application/json; charset=utf-8'},
      );
    });
    await tester.pumpWidget(
      MaterialApp(
        home: ChatScreen(client: client, apiBaseUrl: 'http://127.0.0.1:8000'),
      ),
    );
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'Question hors ligne');
    await tester.tap(find.byTooltip('Envoyer'));
    await tester.pump();
    await tester.pumpAndSettle();
    expect(
      find.textContaining('Connexion au serveur impossible'),
      findsOneWidget,
    );
    expect(find.text('Réessayer'), findsOneWidget);

    await tester.tap(find.text('Réessayer'));
    await tester.pump();
    await tester.pumpAndSettle();
    expect(calls, 2);
    expect(find.text('Connexion rétablie.'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('adapts to phone and desktop widths without overflow', (
    tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(390, 844);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(const EmsiChatbotApp());
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('chat-workspace')), findsOneWidget);
    expect(tester.takeException(), isNull);

    tester.view.physicalSize = const Size(1440, 900);
    await tester.pumpAndSettle();
    expect(find.text('VOTRE ASSISTANT'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('mobile drawer opens and its theme switch applies dark mode', (
    tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(390, 844);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(const EmsiChatbotApp());
    await tester.pumpAndSettle();
    expect(
      Theme.of(tester.element(find.byType(Scaffold))).brightness,
      Brightness.light,
    );

    await tester.tap(find.byIcon(Icons.menu));
    await tester.pumpAndSettle();
    expect(find.text('VOTRE ASSISTANT'), findsOneWidget);
    await tester.tap(find.text('Mode sombre'));
    await tester.pumpAndSettle();

    expect(
      Theme.of(tester.element(find.byType(Scaffold))).brightness,
      Brightness.dark,
    );
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}

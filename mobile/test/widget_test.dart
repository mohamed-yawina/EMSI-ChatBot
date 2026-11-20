import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:emsi_chatbot/main.dart';
import 'package:emsi_chatbot/auth/auth_service.dart';
import 'package:emsi_chatbot/theme/app_theme.dart';
import 'package:emsi_chatbot/widgets/markdown_content.dart';
import 'package:emsi_chatbot/models/conversation_models.dart';
import 'package:emsi_chatbot/services/conversation_repository.dart';
import 'package:emsi_chatbot/services/image_selection_service.dart';

import 'support/fake_auth_service.dart';
import 'support/fake_conversation_repository.dart';

void _logRenderFlexDiagnostics(WidgetTester tester, String scenario) {
  final previousHandler = FlutterError.onError;
  FlutterError.onError = (details) {
    if (details.exceptionAsString().contains('RenderFlex overflowed')) {
      debugPrint('RenderFlex diagnostic ($scenario):');
      debugPrint(details.toString());
    }
    if (previousHandler != null) {
      previousHandler(details);
    } else {
      FlutterError.presentError(details);
    }
  };
  addTearDown(() => FlutterError.onError = previousHandler);
}

class _FakeChatImagePicker implements ChatImagePicker {
  _FakeChatImagePicker(this.image);
  final SelectedChatImage image;

  @override
  Future<SelectedChatImage?> pickImage() async => image;
}

void main() {
  test('light and dark themes use the green accessible palette', () {
    final light = AppTheme.light();
    final dark = AppTheme.dark();

    expect(light.useMaterial3, isTrue);
    expect(light.brightness, Brightness.light);
    expect(light.colorScheme.primary, AppTheme.green);
    expect(light.colorScheme.onPrimary, Colors.white);
    expect(light.colorScheme.primaryContainer, AppTheme.lightGreen);
    expect(light.scaffoldBackgroundColor, AppTheme.lightBackground);
    expect(dark.useMaterial3, isTrue);
    expect(dark.brightness, Brightness.dark);
    expect(dark.colorScheme.primary, isNot(light.colorScheme.primary));
    expect(dark.colorScheme.onSurface, isNot(light.colorScheme.onSurface));
  });

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
    final campusSuggestion = find.byKey(const ValueKey('welcome-suggestion-0'));
    await tester.ensureVisible(campusSuggestion);
    await tester.tap(campusSuggestion);
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

  test(
    'restored image paths resolve against FastAPI and retain page metadata',
    () {
      final image = ChatImage.fromJson({
        'url': '/images/Brochure-EMSI/images/page_4.jpg',
        'source': 'Brochure-EMSI.pdf',
        'page': 4,
        'caption': 'Campus EMSI',
        'context': 'Le passage de la page mentionne le campus.',
      }, baseUrl: 'http://127.0.0.1:8000');
      expect(
        image.url,
        'http://127.0.0.1:8000/images/Brochure-EMSI/images/page_4.jpg',
      );
      expect(
        resolveApiImageUrl(image.url, baseUrl: 'http://127.0.0.1:8000'),
        'http://127.0.0.1:8000/images/Brochure-EMSI/images/page_4.jpg',
      );
      expect(image.source, 'Brochure-EMSI.pdf');
      expect(image.page, '4');
      expect(image.caption, isNull);
      expect(image.captionVerified, isFalse);
      expect(image.displayLabel, 'Visuel de la brochure EMSI — page 4');
      expect(image.context, 'Le passage de la page mentionne le campus.');
      final verified = ChatImage.fromJson({
        'url': '/images/Brochure-EMSI/images/page_4.jpg',
        'page': 4,
        'caption': 'Campus EMSI de Rabat',
        'caption_verified': true,
      });
      expect(verified.caption, 'Campus EMSI de Rabat');
      expect(verified.displayLabel, 'Campus EMSI de Rabat');
      expect(
        ChatImage.fromJson({'url': 'https://other.example/image.jpg'}).url,
        isEmpty,
      );
      expect(
        resolveApiImageUrl(
          'https://127.0.0.1:8000/api/chat',
          baseUrl: 'http://127.0.0.1:8000',
        ),
        isEmpty,
      );
      expect(
        resolveApiImageUrl(
          '//other.example/images/photo.jpg',
          baseUrl: 'http://127.0.0.1:8000',
        ),
        isEmpty,
      );
      expect(
        resolveApiImageUrl(
          '/images/../api/chat',
          baseUrl: 'http://127.0.0.1:8000',
        ),
        isEmpty,
      );
    },
  );

  test(
    'restored Supabase image keeps its page and uses a safe fallback label',
    () {
      final message = chatMessageFromStoredJson({
        'role': 'assistant',
        'content': 'Voici un visuel.',
        'created_at': '2026-11-19T10:00:00Z',
        'sources': [
          {'source': 'Brochure-EMSI.pdf', 'page': 9},
        ],
        'images': [
          {
            'url': '/images/Brochure-EMSI/images/page_9_image_1.jpeg',
            'source': 'Brochure-EMSI.pdf',
            'page': 9,
            'context': 'La page évoque les campus.',
          },
        ],
      }, imageBaseUrl: 'http://127.0.0.1:8000');

      expect(message.images, hasLength(1));
      expect(message.images.single.page, '9');
      expect(
        message.images.single.displayLabel,
        'Visuel de la brochure EMSI — page 9',
      );
      expect(message.sources.single.page, '9');
    },
  );

  test(
    'restored private upload accepts only this project signed image URL',
    () {
      final own = chatMessageFromStoredJson({
        'role': 'user',
        'content': 'Explique cette image.',
        'created_at': '2026-11-19T10:00:00Z',
        'images': [
          {
            'url': 'https://project.supabase.co/storage/v1/object/sign/chat-uploads/user/conversation/image.jpg?token=short-lived',
            'bucket': 'chat-uploads',
            'storage_path': 'user/conversation/image.jpg',
          },
        ],
      }, trustedStorageBaseUrl: 'https://project.supabase.co');
      expect(own.images, hasLength(1));
      expect(own.images.single.url, startsWith('https://project.supabase.co/'));

      final external = chatMessageFromStoredJson({
        'role': 'user',
        'content': 'Image externe.',
        'created_at': '2026-11-19T10:00:00Z',
        'images': [
          {
            'url': 'https://attacker.example/storage/v1/object/sign/chat-uploads/x.jpg?token=x',
          },
        ],
      }, trustedStorageBaseUrl: 'https://project.supabase.co');
      expect(external.images, isEmpty);
    },
  );

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

  test('history search targets title and full text case-insensitively', () {
    final filter = buildConversationSearchFilter('  Campus  ');
    expect(filter, contains('title.ilike."%Campus%"'));
    expect(filter, contains('search_text.ilike."%Campus%"'));
    expect(filter, isNot(contains('.like.')));
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

      await tester.tap(find.byKey(const ValueKey('appbar-new-conversation')));
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
    expect(
      find.text(
        'Les images de la brochure ne sont pas accessibles pour le moment.',
      ),
      findsOneWidget,
    );
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
    _logRenderFlexDiagnostics(tester, 'phone and desktop responsive test');
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(390, 844);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final auth = FakeAuthService(
      user: const AuthUserInfo(id: 'widget-user', email: 'demo@example.test'),
    );
    addTearDown(auth.dispose);
    await tester.pumpWidget(EmsiChatbotApp(authService: auth));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('chat-workspace')), findsOneWidget);
    const responsiveSizes = [
      Size(320, 568),
      Size(375, 812),
      Size(390, 844),
      Size(420, 900),
      Size(768, 1024),
    ];
    for (final size in responsiveSizes) {
      tester.view.physicalSize = size;
      await tester.pumpAndSettle();
      expect(
        find.byKey(const ValueKey('chat-workspace')),
        findsOneWidget,
        reason: 'Chat workspace at ${size.width}x${size.height}',
      );
      expect(
        tester.takeException(),
        isNull,
        reason: 'No layout exception at ${size.width}x${size.height}',
      );
    }

    tester.view.physicalSize = const Size(800, 900);
    await tester.pumpAndSettle();
    expect(
      find.byTooltip('Dashboard — indisponible actuellement'),
      findsOneWidget,
    );
    expect(
      find.byTooltip('Historique — indisponible actuellement'),
      findsOneWidget,
    );
    expect(tester.takeException(), isNull);

    tester.view.physicalSize = const Size(1440, 900);
    await tester.pumpAndSettle();
    expect(find.text('VOTRE ASSISTANT'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('guest-backed screen keeps account features unavailable', (
    tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(1440, 900);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final auth = FakeAuthService(
      user: const AuthUserInfo(id: 'widget-user', email: 'demo@example.test'),
    );
    addTearDown(auth.dispose);
    await tester.pumpWidget(EmsiChatbotApp(authService: auth));
    await tester.pumpAndSettle();

    expect(find.text('Dashboard'), findsOneWidget);
    expect(find.text('Historique'), findsOneWidget);
    expect(find.byKey(const ValueKey('dashboard-user-email')), findsNothing);
    expect(find.byKey(const ValueKey('sidebar-profile-email')), findsOneWidget);
    expect(find.text('demo@example.test'), findsOneWidget);
    final uploadButton = tester.widget<IconButton>(
      find.widgetWithIcon(IconButton, Icons.add_photo_alternate_outlined),
    );
    expect(uploadButton.onPressed, isNotNull);
    expect(
      find.byTooltip('Joindre une image JPEG, PNG ou WebP (5 Mo max.)'),
      findsOneWidget,
    );
    await tester.tap(find.byKey(const ValueKey('attach-image-button')));
    await tester.pumpAndSettle();
    expect(
      find.text('Connectez-vous pour joindre une image à une conversation.'),
      findsOneWidget,
    );
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('authenticated user can preview, remove and upload an image', (
    tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(320, 568);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final png = base64Decode(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/h00AAAAASUVORK5CYII=',
    );
    final selected = SelectedChatImage(
      bytes: png,
      mimeType: 'image/png',
      fileName: 'diagram.png',
    );
    final repository = FakeConversationRepository();
    String? requestPath;
    String? requestMethod;
    String? requestContentType;
    String? authorization;
    String? requestBody;
    List<int>? requestBytes;
    final requestCompleted = Completer<void>();
    final client = MockClient((request) async {
      requestPath = request.url.path;
      requestMethod = request.method;
      requestContentType = request.headers['content-type'];
      authorization = request.headers['authorization'];
      requestBytes = request.bodyBytes;
      // Multipart contains binary PNG bytes as well as UTF-8 text fields.
      requestBody = utf8.decode(requestBytes!, allowMalformed: true);
      if (!requestCompleted.isCompleted) requestCompleted.complete();
      return http.Response(
        '{"answer":"Le schéma montre une forme simple.","sources":[],"images":[]}',
        200,
        headers: {'content-type': 'application/json; charset=utf-8'},
      );
    });
    addTearDown(client.close);
    await tester.pumpWidget(
      MaterialApp(
        home: ChatScreen(
          client: client,
          apiBaseUrl: 'http://127.0.0.1:8000',
          conversationRepository: repository,
          accessTokenProvider: () => 'signed-test-token',
          imagePicker: _FakeChatImagePicker(selected),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('dashboard-new-conversation')));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('attach-image-button')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('remove-selected-image')), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('remove-selected-image')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('remove-selected-image')), findsNothing);

    await tester.tap(find.byKey(const ValueKey('attach-image-button')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, 'Explique ce schéma.');
    await tester.tap(find.byTooltip('Envoyer'));
    await tester.pumpAndSettle();
    await requestCompleted.future.timeout(const Duration(seconds: 1));

    expect(requestMethod, 'POST');
    expect(requestContentType, startsWith('multipart/form-data;'));
    expect(
      requestPath,
      endsWith(
        '/api/conversations/${repository.conversations.first.id}/vision',
      ),
    );
    expect(authorization, 'Bearer signed-test-token');
    expect(requestBody, contains('name="question"'));
    expect(requestBody, contains('Explique ce schéma.'));
    expect(requestBody, contains('name="image"'));
    expect(requestBody, contains('filename="upload"'));
    expect(
      requestBytes,
      containsAllInOrder(png.take(8)),
      reason: 'The multipart body should include the PNG signature.',
    );
    expect(find.text('Le schéma montre une forme simple.'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('mobile drawer opens and its theme switch applies dark mode', (
    tester,
  ) async {
    _logRenderFlexDiagnostics(tester, 'mobile drawer and theme test');
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(390, 844);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final auth = FakeAuthService(
      user: const AuthUserInfo(id: 'widget-user', email: 'demo@example.test'),
    );
    addTearDown(auth.dispose);
    await tester.pumpWidget(EmsiChatbotApp(authService: auth));
    await tester.pumpAndSettle();
    for (final width in [320.0, 375.0, 390.0, 420.0]) {
      tester.view.physicalSize = Size(width, 844);
      await tester.pumpAndSettle();
      expect(
        tester.takeException(),
        isNull,
        reason: 'No layout exception before opening drawer at $width px',
      );
    }
    for (final width in [320.0, 375.0, 390.0, 420.0]) {
      tester.view.physicalSize = Size(width, 844);
      await tester.pumpAndSettle();
      await tester.tap(find.byIcon(Icons.menu));
      await tester.pumpAndSettle();
      expect(find.text('VOTRE ASSISTANT'), findsOneWidget);
      expect(
        tester.takeException(),
        isNull,
        reason: 'No drawer layout exception at $width px',
      );
      tester.state<ScaffoldState>(find.byType(Scaffold)).closeDrawer();
      await tester.pumpAndSettle();
    }
    tester.view.physicalSize = const Size(390, 844);
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

  testWidgets('personal dashboard uses saved stats and opens a saved chat', (
    tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(1440, 900);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final conversation = ConversationSummary(
      id: 'conversation-a',
      title: 'Campus EMSI',
      isArchived: false,
      isFavorite: true,
      createdAt: DateTime(2026, 11, 18),
      updatedAt: DateTime(2026, 11, 18),
      messageCount: 2,
      lastMessage: 'Rabat est mentionné page 4.',
    );
    final repository = FakeConversationRepository(
      initialConversations: [conversation],
      initialMessages: {
        conversation.id: [
          ChatMessage(text: 'Quels campus ?', isUser: true),
          ChatMessage(
            text: 'Rabat est mentionné page 4.',
            isUser: false,
            sources: const [ChatSource(name: 'Brochure-EMSI.pdf', page: '4')],
          ),
        ],
      },
      stats: DashboardStats(
        conversationCount: 1,
        messageCount: 2,
        favoriteCount: 1,
        lastActivity: DateTime(2026, 11, 18),
      ),
    );

    await tester.pumpWidget(
      MaterialApp(
        home: ChatScreen(
          conversationRepository: repository,
          profileEmail: 'demo@example.test',
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('dashboard-user-email')), findsOneWidget);
    expect(find.byKey(const ValueKey('sidebar-profile-email')), findsOneWidget);
    expect(find.text('demo@example.test'), findsNWidgets(2));
    expect(find.text('Conversations'), findsWidgets);
    expect(
      find.byKey(const ValueKey('dashboard-conversation-conversation-a')),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: find.byKey(const ValueKey('dashboard-conversation-conversation-a')),
        matching: find.textContaining('Rabat est mentionné'),
      ),
      findsOneWidget,
    );
    tester.view.physicalSize = const Size(390, 844);
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    tester.view.physicalSize = const Size(1440, 900);
    await tester.pumpAndSettle();
    await tester.tap(
      find.byKey(const ValueKey('dashboard-conversation-conversation-a')),
    );
    await tester.pumpAndSettle();
    expect(find.text('Quels campus ?'), findsOneWidget);
    expect(
      find.descendant(
        of: find.byKey(const ValueKey('chat-message-assistant-1')),
        matching: find.textContaining('Rabat est mentionné'),
      ),
      findsOneWidget,
    );
    expect(find.text('Brochure-EMSI.pdf · page 4'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('persistent chat creates a conversation and sends its JWT', (
    tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(1440, 900);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    Map<String, dynamic>? requestBody;
    String? authorization;
    final client = MockClient((request) async {
      requestBody = jsonDecode(request.body) as Map<String, dynamic>;
      authorization = request.headers['authorization'];
      return http.Response(
        jsonEncode({
          'answer': 'La réponse est fondée sur la brochure.',
          'sources': [
            {'source': 'Brochure-EMSI.pdf', 'page': 8},
          ],
          'images': [],
        }),
        200,
        headers: {'content-type': 'application/json; charset=utf-8'},
      );
    });
    final repository = FakeConversationRepository();
    await tester.pumpWidget(
      MaterialApp(
        home: ChatScreen(
          client: client,
          apiBaseUrl: 'http://127.0.0.1:8000',
          conversationRepository: repository,
          accessTokenProvider: () => 'test-access-token',
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('dashboard-new-conversation')));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byType(TextField).last,
      'Quels campus sont mentionnés ?',
    );
    await tester.tap(find.byTooltip('Envoyer'));
    await tester.pumpAndSettle();

    expect(repository.conversations, hasLength(1));
    expect(requestBody!['question'], 'Quels campus sont mentionnés ?');
    expect(requestBody!['request_id'], isA<String>());
    expect(requestBody!.containsKey('history'), isFalse);
    expect(requestBody!['include_images'], isFalse);
    expect(authorization, 'Bearer test-access-token');
    expect(find.text('La réponse est fondée sur la brochure.'), findsOneWidget);
    expect(find.text('Brochure-EMSI.pdf · page 8'), findsOneWidget);
  });

  testWidgets(
    'conversation search, favorite, archive, rename and delete work',
    (tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(1440, 900);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final conversation = ConversationSummary(
        id: 'conversation-actions',
        title: 'Campus EMSI',
        isArchived: false,
        isFavorite: false,
        createdAt: DateTime(2026, 11, 18),
        updatedAt: DateTime(2026, 11, 18),
        messageCount: 0,
      );
      final repository = FakeConversationRepository(
        initialConversations: [conversation],
        initialMessages: {
          conversation.id: [
            ChatMessage(
              text: 'Phrase avec un contenu spécifique',
              isUser: false,
            ),
          ],
        },
      );
      await tester.pumpWidget(
        MaterialApp(home: ChatScreen(conversationRepository: repository)),
      );
      await tester.pumpAndSettle();

      await tester.enterText(
        find.byKey(const ValueKey('conversation-search')),
        'CONTENU SPÉCIFIQUE',
      );
      await tester.pump(const Duration(milliseconds: 350));
      await tester.pumpAndSettle();
      expect(find.text('Campus EMSI'), findsWidgets);

      await tester.enterText(
        find.byKey(const ValueKey('conversation-search')),
        'Campus EMSI',
      );
      await tester.pump(const Duration(milliseconds: 350));
      await tester.pumpAndSettle();
      expect(
        find.byKey(const ValueKey('sidebar-conversation-conversation-actions')),
        findsOneWidget,
      );

      await tester.enterText(
        find.byKey(const ValueKey('conversation-search')),
        'no match',
      );
      await tester.pump(const Duration(milliseconds: 350));
      await tester.pumpAndSettle();
      expect(find.text('Campus EMSI'), findsNothing);
      expect(find.text('Aucun résultat pour cette recherche.'), findsOneWidget);
      await tester.tap(find.byTooltip('Effacer la recherche'));
      await tester.pump(const Duration(milliseconds: 350));
      await tester.pumpAndSettle();
      expect(find.text('Campus EMSI'), findsWidgets);

      Future<void> chooseAction(String action) async {
        await tester.tap(find.byTooltip('Actions sur la conversation').first);
        await tester.pumpAndSettle();
        await tester.tap(find.text(action).last);
        await tester.pumpAndSettle();
      }

      await chooseAction('Ajouter aux favoris');
      expect(repository.conversations.single.isFavorite, isTrue);
      await chooseAction('Archiver');
      expect(repository.conversations.single.isArchived, isTrue);
      expect(find.text('Campus EMSI'), findsNothing);

      await tester.tap(find.text('Archivées'));
      await tester.pumpAndSettle();
      expect(find.text('Campus EMSI'), findsWidgets);
      await chooseAction('Restaurer');
      expect(repository.conversations.single.isArchived, isFalse);
      await tester.tap(find.text('Actives'));
      await tester.pumpAndSettle();
      await chooseAction('Renommer');
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byKey(const ValueKey('rename-title-field')),
        'Campus de Rabat',
      );
      await tester.tap(find.text('Enregistrer'));
      await tester.pumpAndSettle();
      expect(repository.conversations.single.title, 'Campus de Rabat');

      await chooseAction('Supprimer');
      await tester.pumpAndSettle();
      await tester.tap(find.text('Supprimer').last);
      await tester.pumpAndSettle();
      expect(repository.conversations, isEmpty);
      expect(
        repository.events.any((event) => event.startsWith('delete:')),
        isTrue,
      );
      expect(tester.takeException(), isNull);
    },
  );
}

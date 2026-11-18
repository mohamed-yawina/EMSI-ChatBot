import 'package:flutter/material.dart';

import 'screens/chat_screen.dart';
import 'theme/app_theme.dart';

export 'models/chat_models.dart';
export 'screens/chat_screen.dart';
export 'services/chat_api_service.dart'
    show ChatApiService, ChatRequestException;
export 'widgets/chat_message_bubble.dart' show ImageGallery;

void main() => runApp(const EmsiChatbotApp());

class EmsiChatbotApp extends StatefulWidget {
  const EmsiChatbotApp({super.key});

  @override
  State<EmsiChatbotApp> createState() => _EmsiChatbotAppState();
}

class _EmsiChatbotAppState extends State<EmsiChatbotApp> {
  ThemeMode _themeMode = ThemeMode.light;

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'EMSI-ChatBot',
    debugShowCheckedModeBanner: false,
    theme: AppTheme.light(),
    darkTheme: AppTheme.dark(),
    themeMode: _themeMode,
    home: ChatScreen(
      themeMode: _themeMode,
      onThemeModeChanged: (mode) => setState(() => _themeMode = mode),
    ),
  );
}

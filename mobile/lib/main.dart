import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_web_plugins/url_strategy.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import 'app/supabase_config.dart';
import 'auth/auth_service.dart';
import 'auth/auth_gate.dart';
import 'services/supabase_auth_service.dart';
import 'theme/app_theme.dart';
import 'widgets/auth_screen_widgets.dart';

export 'models/chat_models.dart';
export 'screens/chat_screen.dart';
export 'services/chat_api_service.dart'
    show ChatApiService, ChatRequestException;
export 'widgets/chat_message_bubble.dart' show ImageGallery;

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  if (kIsWeb) usePathUrlStrategy();

  if (!SupabaseConfig.isConfigured) {
    runApp(const EmsiChatbotApp(configurationMissing: true));
    return;
  }

  try {
    await Supabase.initialize(
      url: SupabaseConfig.url,
      publishableKey: SupabaseConfig.publishableKey,
      authOptions: const FlutterAuthClientOptions(
        authFlowType: AuthFlowType.pkce,
      ),
    );
    runApp(
      EmsiChatbotApp(
        authService: SupabaseAuthService(Supabase.instance.client),
        supabaseClient: Supabase.instance.client,
      ),
    );
  } catch (_) {
    runApp(const EmsiChatbotApp(initializationFailed: true));
  }
}

class EmsiChatbotApp extends StatefulWidget {
  const EmsiChatbotApp({
    super.key,
    this.authService,
    this.configurationMissing = false,
    this.initializationFailed = false,
    this.supabaseClient,
  });

  final AuthService? authService;
  final bool configurationMissing;
  final bool initializationFailed;
  final SupabaseClient? supabaseClient;

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
    home: widget.configurationMissing
        ? const AuthConfigMissingPage()
        : widget.initializationFailed
        ? const AuthInitializationErrorPage()
        : widget.authService == null
        ? const AuthConfigMissingPage()
        : AuthGate(
            authService: widget.authService!,
            supabaseClient: widget.supabaseClient,
            themeMode: _themeMode,
            onThemeModeChanged: (mode) => setState(() => _themeMode = mode),
          ),
  );
}

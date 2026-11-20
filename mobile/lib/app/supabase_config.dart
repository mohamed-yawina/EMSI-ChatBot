class SupabaseConfig {
  static const url = String.fromEnvironment('SUPABASE_URL');
  static const publishableKey = String.fromEnvironment(
    'SUPABASE_PUBLISHABLE_KEY',
  );

  static const mobileRedirectUrl = 'com.emsi.chatbot://login-callback/';

  static bool get isConfigured =>
      _isProjectUrl(url) && _isPublishableKey(publishableKey);

  static bool _isProjectUrl(String value) {
    final uri = Uri.tryParse(value);
    return uri != null &&
        uri.scheme == 'https' &&
        uri.host.isNotEmpty &&
        uri.path.isEmpty &&
        uri.query.isEmpty &&
        uri.fragment.isEmpty;
  }

  static bool _isPublishableKey(String value) =>
      value.startsWith('sb_publishable_') &&
      !value.contains('replace_with_') &&
      value.length > 'sb_publishable_'.length;
}

import 'package:flutter/foundation.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import '../app/supabase_config.dart';
import '../auth/auth_service.dart';

class SupabaseAuthService implements AuthService {
  SupabaseAuthService(this._client);

  final SupabaseClient _client;
  bool _needsPasswordUpdate = false;

  static String get _redirectUrl =>
      kIsWeb ? Uri.base.origin : SupabaseConfig.mobileRedirectUrl;

  AuthUserInfo? _mapUser(User? user) =>
      user == null ? null : AuthUserInfo(id: user.id, email: user.email);

  @override
  AuthSnapshot get currentState => AuthSnapshot(
    user: _mapUser(_client.auth.currentUser),
    needsPasswordUpdate: _needsPasswordUpdate,
  );

  @override
  Stream<AuthSnapshot> get authStateChanges =>
      _client.auth.onAuthStateChange.map((state) {
        if (state.event == AuthChangeEvent.passwordRecovery) {
          _needsPasswordUpdate = true;
        } else if (state.event == AuthChangeEvent.signedOut ||
            state.event == AuthChangeEvent.userUpdated) {
          _needsPasswordUpdate = false;
        }
        return AuthSnapshot(
          user: _mapUser(state.session?.user ?? _client.auth.currentUser),
          needsPasswordUpdate: _needsPasswordUpdate,
        );
      });

  @override
  Future<AuthActionResult> signIn({
    required String email,
    required String password,
  }) async {
    try {
      await _client.auth.signInWithPassword(email: email, password: password);
      return const AuthActionResult(
        succeeded: true,
        message: 'Connexion réussie.',
      );
    } on AuthException catch (error) {
      return AuthActionResult(succeeded: false, message: _friendlyError(error));
    } catch (_) {
      return const AuthActionResult(
        succeeded: false,
        message: 'Connexion impossible. Vérifiez votre réseau et réessayez.',
      );
    }
  }

  @override
  Future<AuthActionResult> register({
    required String email,
    required String password,
  }) async {
    try {
      final response = await _client.auth.signUp(
        email: email,
        password: password,
        emailRedirectTo: _redirectUrl,
      );
      return AuthActionResult(
        succeeded: true,
        message: response.session == null
            ? 'Inscription reçue. Consultez votre boîte e-mail pour confirmer votre adresse avant de vous connecter.'
            : 'Compte créé et connecté.',
      );
    } on AuthException catch (error) {
      return AuthActionResult(succeeded: false, message: _friendlyError(error));
    } catch (_) {
      return const AuthActionResult(
        succeeded: false,
        message: 'Inscription impossible. Vérifiez votre réseau et réessayez.',
      );
    }
  }

  @override
  Future<AuthActionResult> requestPasswordReset({required String email}) async {
    try {
      await _client.auth.resetPasswordForEmail(email, redirectTo: _redirectUrl);
      return const AuthActionResult(
        succeeded: true,
        message: 'Si cette adresse correspond à un compte, un lien de réinitialisation va être envoyé.',
      );
    } on AuthException catch (error) {
      return AuthActionResult(succeeded: false, message: _friendlyError(error));
    } catch (_) {
      return const AuthActionResult(
        succeeded: false,
        message: 'Demande impossible. Vérifiez votre réseau et réessayez.',
      );
    }
  }

  @override
  Future<AuthActionResult> updateRecoveryPassword({
    required String password,
  }) async {
    try {
      await _client.auth.updateUser(UserAttributes(password: password));
      _needsPasswordUpdate = false;
      return const AuthActionResult(
        succeeded: true,
        message: 'Votre mot de passe a été mis à jour.',
      );
    } on AuthException catch (error) {
      return AuthActionResult(succeeded: false, message: _friendlyError(error));
    } catch (_) {
      return const AuthActionResult(
        succeeded: false,
        message: 'Mise à jour impossible. Vérifiez votre réseau et réessayez.',
      );
    }
  }

  @override
  Future<AuthActionResult> signOut() async {
    try {
      await _client.auth.signOut();
      _needsPasswordUpdate = false;
      return const AuthActionResult(
        succeeded: true,
        message: 'Déconnexion réussie.',
      );
    } on AuthException catch (error) {
      return AuthActionResult(succeeded: false, message: _friendlyError(error));
    } catch (_) {
      return const AuthActionResult(
        succeeded: false,
        message: 'Déconnexion impossible. Réessayez.',
      );
    }
  }

  String _friendlyError(AuthException error) {
    final message = error.message.toLowerCase();
    if (message.contains('invalid login credentials') ||
        message.contains('invalid credentials')) {
      return 'Adresse e-mail ou mot de passe incorrect.';
    }
    if (message.contains('email not confirmed') ||
        message.contains('email_not_confirmed')) {
      return 'Confirmez votre adresse e-mail à partir du lien reçu avant de vous connecter.';
    }
    if (message.contains('password') &&
        (message.contains('length') || message.contains('weak'))) {
      return 'Choisissez un mot de passe plus long et plus robuste.';
    }
    if (message.contains('rate limit') ||
        message.contains('too many requests')) {
      return 'Trop de tentatives. Attendez un peu avant de réessayer.';
    }
    return 'La demande n’a pas abouti. Vérifiez les informations puis réessayez.';
  }
}

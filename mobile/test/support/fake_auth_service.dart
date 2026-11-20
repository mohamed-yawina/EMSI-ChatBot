import 'dart:async';

import 'package:emsi_chatbot/auth/auth_service.dart';

class FakeAuthService implements AuthService {
  FakeAuthService({AuthUserInfo? user}) : _state = AuthSnapshot(user: user);

  AuthSnapshot _state;
  final StreamController<AuthSnapshot> _events =
      StreamController<AuthSnapshot>.broadcast();
  int signInCalls = 0;
  int registerCalls = 0;
  int resetCalls = 0;
  int signOutCalls = 0;
  AuthActionResult nextResult = const AuthActionResult(
    succeeded: true,
    message: 'Action terminée.',
  );

  @override
  AuthSnapshot get currentState => _state;

  @override
  Stream<AuthSnapshot> get authStateChanges => _events.stream;

  void setState(AuthSnapshot state) {
    _state = state;
    _events.add(state);
  }

  @override
  Future<AuthActionResult> signIn({
    required String email,
    required String password,
  }) async {
    signInCalls++;
    if (nextResult.succeeded) {
      setState(
        AuthSnapshot(
          user: AuthUserInfo(id: 'test-user', email: email),
        ),
      );
    }
    return nextResult;
  }

  @override
  Future<AuthActionResult> register({
    required String email,
    required String password,
  }) async {
    registerCalls++;
    return nextResult;
  }

  @override
  Future<AuthActionResult> requestPasswordReset({required String email}) async {
    resetCalls++;
    return nextResult;
  }

  @override
  Future<AuthActionResult> updateRecoveryPassword({
    required String password,
  }) async => nextResult;

  @override
  Future<AuthActionResult> signOut() async {
    signOutCalls++;
    if (nextResult.succeeded) setState(const AuthSnapshot());
    return nextResult;
  }

  Future<void> dispose() => _events.close();
}

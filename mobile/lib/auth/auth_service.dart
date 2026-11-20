class AuthUserInfo {
  const AuthUserInfo({required this.id, required this.email});

  final String id;
  final String? email;
}

class AuthSnapshot {
  const AuthSnapshot({this.user, this.needsPasswordUpdate = false});

  final AuthUserInfo? user;
  final bool needsPasswordUpdate;
}

class AuthActionResult {
  const AuthActionResult({required this.succeeded, required this.message});

  final bool succeeded;
  final String message;
}

abstract interface class AuthService {
  AuthSnapshot get currentState;

  Stream<AuthSnapshot> get authStateChanges;

  Future<AuthActionResult> signIn({
    required String email,
    required String password,
  });

  Future<AuthActionResult> register({
    required String email,
    required String password,
  });

  Future<AuthActionResult> requestPasswordReset({required String email});

  Future<AuthActionResult> updateRecoveryPassword({required String password});

  Future<AuthActionResult> signOut();
}

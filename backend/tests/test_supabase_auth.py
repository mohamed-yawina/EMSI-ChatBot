import json
import sys
from pathlib import Path

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.security.supabase_jwt import SupabaseJWKSVerifier, SupabaseTokenInvalid


PROJECT_URL = "https://example-project.supabase.co"
ISSUER = f"{PROJECT_URL}/auth/v1"


@pytest.fixture
def key_pair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": "test-key", "use": "sig", "alg": "RS256"})
    return private_key, public_jwk


def _token(private_key, **claim_overrides):
    claims = {
        "iss": ISSUER,
        "aud": "authenticated",
        "sub": "user-123",
        "email": "person@example.test",
        "iat": 1_760_000_000,
        "exp": 4_000_000_000,
    }
    claims.update(claim_overrides)
    return jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )


def _verifier(key):
    def handler(request):
        assert request.url.path == "/auth/v1/.well-known/jwks.json"
        return httpx.Response(200, json={"keys": [key]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return SupabaseJWKSVerifier(PROJECT_URL, client=client), client


def test_verifies_signature_and_supabase_identity(key_pair):
    private_key, jwk = key_pair
    verifier, client = _verifier(jwk)
    try:
        identity = verifier.verify(_token(private_key))
    finally:
        client.close()
    assert identity.subject == "user-123"
    assert identity.email == "person@example.test"


def test_verifies_es256_project_signing_key():
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_jwk = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": "test-key", "use": "sig", "alg": "ES256"})
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"keys": [public_jwk]})
        )
    )
    verifier = SupabaseJWKSVerifier(PROJECT_URL, client=client)
    token = jwt.encode(
        {
            "iss": ISSUER,
            "aud": "authenticated",
            "sub": "user-123",
            "exp": 4_000_000_000,
        },
        private_key,
        algorithm="ES256",
        headers={"kid": "test-key"},
    )
    try:
        assert verifier.verify(token).subject == "user-123"
    finally:
        client.close()


@pytest.mark.parametrize(
    "claims",
    [
        {"iss": "https://attacker.example/auth/v1"},
        {"aud": "other"},
        {"exp": 1_000_000_000},
        {"sub": ""},
    ],
)
def test_rejects_invalid_required_claims(key_pair, claims):
    private_key, jwk = key_pair
    verifier, client = _verifier(jwk)
    try:
        with pytest.raises(SupabaseTokenInvalid):
            verifier.verify(_token(private_key, **claims))
    finally:
        client.close()


def test_rejects_tampered_signature(key_pair):
    private_key, jwk = key_pair
    verifier, client = _verifier(jwk)
    token = _token(private_key)
    header, payload, signature = token.split(".")
    altered = f"{header}.{payload}.{('A' if signature[0] != 'A' else 'B')}{signature[1:]}"
    try:
        with pytest.raises(SupabaseTokenInvalid):
            verifier.verify(altered)
    finally:
        client.close()


def test_rejects_hmac_algorithm_even_when_header_is_valid(key_pair):
    private_key, jwk = key_pair
    verifier, client = _verifier(jwk)
    token = jwt.encode(
        {"iss": ISSUER, "aud": "authenticated", "sub": "user-123", "exp": 4_000_000_000},
        "not-a-supabase-key",
        algorithm="HS256",
        headers={"kid": "test-key"},
    )
    try:
        with pytest.raises(SupabaseTokenInvalid):
            verifier.verify(token)
    finally:
        client.close()


def test_profile_endpoint_requires_verified_bearer_and_chat_remains_anonymous(
    key_pair, monkeypatch
):
    private_key, jwk = key_pair
    verifier, client = _verifier(jwk)
    from app.api import auth
    from app import main

    monkeypatch.setattr(auth, "get_supabase_verifier", lambda: verifier)
    monkeypatch.setattr(main, "get_cached_rag_answer", lambda question, use_llm: ("ok", []))
    with TestClient(main.app) as api:
        no_auth = api.get("/api/users/me")
        profile = api.get(
            "/api/users/me",
            headers={"Authorization": f"Bearer {_token(private_key)}"},
        )
        anonymous_chat = api.post("/api/chat", json={"question": "test"})
    client.close()

    assert no_auth.status_code == 401
    assert profile.status_code == 200
    assert profile.json() == {"id": "user-123", "email": "person@example.test"}
    assert anonymous_chat.status_code == 200
    assert anonymous_chat.json() == {"answer": "ok", "sources": [], "images": []}


def test_profile_endpoint_returns_503_when_jwks_is_unavailable(key_pair, monkeypatch):
    private_key, _ = key_pair
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(503, json={"error": "unavailable"})
        )
    )
    verifier = SupabaseJWKSVerifier(PROJECT_URL, client=client)
    from app.api import auth
    from app.main import app

    monkeypatch.setattr(auth, "get_supabase_verifier", lambda: verifier)
    with TestClient(app) as api:
        response = api.get(
            "/api/users/me",
            headers={"Authorization": f"Bearer {_token(private_key)}"},
        )
    client.close()
    assert response.status_code == 503
    assert response.json() == {
        "detail": "Supabase authentication is temporarily unavailable."
    }

from io import BytesIO
import json
from pathlib import Path
import sys
import time
from uuid import UUID

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.vision_service import (
    VisionInputError,
    VisionProviderError,
    generate_image_answer,
    validate_image,
)
from app.security.supabase_jwt import SupabaseJWKSVerifier


PROJECT_URL = "https://vision-test.supabase.co"
ISSUER = f"{PROJECT_URL}/auth/v1"
CONVERSATION_ID = "99000000-0000-4000-8000-000000000001"


class FakeVisionConversationStore:
    """In-memory persistence fake for the authenticated Vision route tests."""

    def __init__(self):
        self.user_images = {}
        self.user_questions = {}
        self.reply = None

    def assert_owned(self, conversation_id, user_id):
        if user_id != "owner-123":
            from app.services.conversation_store import ConversationNotFound

            raise ConversationNotFound()

    def get_user_message(self, conversation_id, user_id, request_id):
        request_key = str(request_id)
        content = self.user_questions.get(request_key)
        if content is None:
            return None
        return {
            "content": content,
            "images": self.user_images.get(request_key, []),
        }

    def get_reply(self, conversation_id, user_id, request_id):
        return self.reply

    def save_user_message(
        self, conversation_id, user_id, request_id, content, images=None
    ):
        request_key = str(request_id)
        self.user_questions[request_key] = content
        self.user_images[request_key] = images or []

    def touch_conversation(self, conversation_id, user_id, *, proposed_title):
        pass

    def save_assistant_message(
        self, conversation_id, user_id, request_id, content, sources, images
    ):
        self.reply = {"content": content, "sources": sources, "images": images}
        return self.reply


@pytest.fixture
def api_context(monkeypatch):
    """Build FastAPI with signed test JWTs and mocked persistence/JWKS only."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = json.loads(
        jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key())
    )
    public_key.update({"kid": "vision-test-key", "use": "sig", "alg": "RS256"})

    def make_token(subject="owner-123"):
        now = int(time.time())
        return jwt.encode(
            {
                "iss": ISSUER,
                "aud": "authenticated",
                "sub": subject,
                "email": f"{subject}@example.test",
                "iat": now - 1,
                "exp": now + 3600,
            },
            private_key,
            algorithm="RS256",
            headers={"kid": "vision-test-key"},
        )

    jwks_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"keys": [public_key]})
        )
    )
    verifier = SupabaseJWKSVerifier(PROJECT_URL, client=jwks_client)
    from app.api import auth, conversations
    from app import main

    store = FakeVisionConversationStore()
    monkeypatch.setattr(auth, "get_supabase_verifier", lambda: verifier)
    monkeypatch.setattr(conversations, "get_conversation_store", lambda: store)
    api = TestClient(main.app)
    return api, make_token, store, main, jwks_client


def png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (8, 6), color="green").save(output, format="PNG")
    return output.getvalue()


def test_image_validator_checks_real_format_and_dimensions():
    mime_type, extension, width, height = validate_image(png_bytes())
    assert (mime_type, extension, width, height) == ("image/png", ".png", 8, 6)
    with pytest.raises(VisionInputError, match="corrompu"):
        validate_image(b"not an image")


def test_image_size_limit_is_enforced_before_decode(monkeypatch):
    monkeypatch.setenv("VISION_MAX_UPLOAD_BYTES", "1024")
    with pytest.raises(VisionInputError, match="taille maximale"):
        validate_image(b"x" * 1025)


def test_vision_request_uses_configured_model_and_image_data_uri(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-secret-never-log")
    monkeypatch.setenv("GROQ_VISION_MODEL", "qwen/qwen3.8-27b")
    captured = {}

    def handler(request):
        captured["authorization"] = request.headers["authorization"]
        captured["body"] = request.read().decode()
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "Une image verte."}}]}
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        answer = generate_image_answer(
            "Que contient cette image ?", png_bytes(), "image/png", client=client
        )
    finally:
        client.close()
    assert answer == "Une image verte."
    assert captured["authorization"] == "Bearer test-secret-never-log"
    assert '"model":"qwen/qwen3.8-27b"' in captured["body"]
    assert "data:image/png;base64," in captured["body"]
    assert "Que contient cette image ?" in captured["body"]


def test_vision_quota_error_is_reported_without_response_body(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-secret-never-log")
    monkeypatch.setenv("GROQ_VISION_MODEL", "qwen/qwen3.8-27b")
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(429, text="secret upstream details")
        )
    )
    try:
        with pytest.raises(VisionProviderError) as error:
            generate_image_answer("Question", png_bytes(), "image/png", client=client)
    finally:
        client.close()
    assert error.value.status_code == 429
    assert "secret" not in str(error.value).lower()


def test_authenticated_vision_route_persists_private_image_and_answer(
    api_context, monkeypatch
):
    api, make_token, store, _main, jwks_client = api_context
    from app.services import vision_service

    uploaded = []

    class FakeStorage:
        def upload(self, metadata, data):
            uploaded.append((metadata, data))

    monkeypatch.setattr(vision_service, "get_private_image_storage", FakeStorage)
    monkeypatch.setattr(
        vision_service,
        "generate_image_answer",
        lambda question, data, mime_type: "L’image montre un schéma.",
    )
    response = api.post(
        f"/api/conversations/{UUID('99000000-0000-4000-8000-000000000001')}/vision",
        headers={"Authorization": f"Bearer {make_token()}"},
        data={
            "question": "Explique-moi ce schéma.",
            "request_id": "99000000-0000-4000-8000-000000000002",
        },
        files={"image": ("original-name.png", png_bytes(), "image/png")},
    )
    jwks_client.close()

    assert response.status_code == 200
    assert response.json() == {"answer": "L’image montre un schéma.", "sources": [], "images": []}
    assert len(uploaded) == 1
    metadata, data = uploaded[0]
    assert metadata["bucket"] == "chat-uploads"
    assert metadata["storage_path"].startswith("owner-123/")
    assert "original-name.png" not in metadata["storage_path"]
    assert data == png_bytes()
    assert store.user_images["99000000-0000-4000-8000-000000000002"] == [metadata]
    assert store.reply["content"] == "L’image montre un schéma."


def test_vision_route_rejects_anonymous_and_non_image_upload(api_context):
    api, make_token, _store, _main, jwks_client = api_context
    path = "/api/conversations/99000000-0000-4000-8000-000000000001/vision"
    form = {
        "question": "Que vois-tu ?",
        "request_id": "99000000-0000-4000-8000-000000000003",
    }
    anonymous = api.post(path, data=form, files={"image": ("a.png", png_bytes())})
    invalid = api.post(
        path,
        headers={"Authorization": f"Bearer {make_token()}"},
        data=form,
        files={"image": ("a.png", b"not-an-image", "image/png")},
    )
    other_user = api.post(
        path,
        headers={"Authorization": f"Bearer {make_token(subject='other-user')}"},
        data=form,
        files={"image": ("a.png", png_bytes(), "image/png")},
    )
    jwks_client.close()
    assert anonymous.status_code == 401
    assert invalid.status_code == 415
    assert other_user.status_code == 404


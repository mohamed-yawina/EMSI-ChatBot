import json
import sys
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.security.supabase_jwt import SupabaseJWKSVerifier
from app.services.conversation_store import ConversationNotFound


PROJECT_URL = "https://mission20-test.supabase.co"
ISSUER = f"{PROJECT_URL}/auth/v1"
CONVERSATION_ID = UUID("99000000-0000-4000-8000-000000000001")
REQUEST_ID = UUID("99000000-0000-4000-8000-000000000002")


@pytest.fixture(scope="module")
def signed_user():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = json.loads(
        jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key())
    )
    public_key.update({"kid": "mission20-key", "use": "sig", "alg": "RS256"})

    def make_token(subject="owner-123"):
        return jwt.encode(
            {
                "iss": ISSUER,
                "aud": "authenticated",
                "sub": subject,
                "email": f"{subject}@example.test",
                "iat": 1_760_000_000,
                "exp": 4_000_000_000,
            },
            private_key,
            algorithm="RS256",
            headers={"kid": "mission20-key"},
        )

    def make_verifier():
        client = httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"keys": [public_key]})
            )
        )
        return SupabaseJWKSVerifier(PROJECT_URL, client=client), client

    return make_token, make_verifier


class FakeConversationStore:
    def __init__(self):
        self.events = []
        self.reply = None
        self.saved_images = None
        self.raise_on_assistant_save = False
        self.user_questions = {}
        self.user_images = {}
        self.history_rows = [
            {"role": "user", "content": "Quels campus ?", "sequence_number": 1},
            {
                "role": "assistant",
                "content": "Rabat et Casablanca. [[REF:A]]",
                "sequence_number": 2,
            },
        ]

    def assert_owned(self, conversation_id, user_id):
        self.events.append(("assert_owned", conversation_id, user_id))
        if user_id != "owner-123":
            raise ConversationNotFound()

    def get_reply(self, conversation_id, user_id, request_id):
        self.events.append(("get_reply", request_id))
        return self.reply

    def get_user_message(self, conversation_id, user_id, request_id):
        content = self.user_questions.get(str(request_id))
        if content is None:
            return None
        return {"content": content, "images": self.user_images.get(str(request_id), [])}

    def assert_request_question(
        self, conversation_id, user_id, request_id, question
    ):
        from app.services.conversation_store import ConversationRequestConflict

        stored = self.user_questions.get(str(request_id))
        if stored != question:
            raise ConversationRequestConflict()

    def load_recent_messages(self, conversation_id, user_id, *, limit):
        self.events.append(("load_recent", limit))
        return self.history_rows

    def save_user_message(self, conversation_id, user_id, request_id, content, images=None):
        self.events.append(("save_user", user_id, request_id, content))
        self.user_questions[str(request_id)] = content
        self.user_images[str(request_id)] = images or []

    def save_assistant_message(
        self, conversation_id, user_id, request_id, content, sources, images
    ):
        self.events.append(("save_assistant", user_id, request_id, content))
        if self.raise_on_assistant_save:
            from app.services.conversation_store import ConversationStoreUnavailable

            raise ConversationStoreUnavailable()
        self.saved_images = images
        self.reply = {"content": content, "sources": sources, "images": images}
        return self.reply

    def touch_conversation(self, conversation_id, user_id, *, proposed_title):
        self.events.append(("touch", proposed_title))


@pytest.fixture
def api_context(monkeypatch, signed_user):
    token_factory, verifier_factory = signed_user
    verifier, client = verifier_factory()
    from app.api import auth
    from app import main

    monkeypatch.setattr(auth, "get_supabase_verifier", lambda: verifier)
    store = FakeConversationStore()
    from app.api import conversations

    monkeypatch.setattr(conversations, "get_conversation_store", lambda: store)
    return TestClient(main.app), token_factory, store, main, client


def test_persistent_chat_verifies_owner_persists_and_restores_five_exchange_history(
    api_context, monkeypatch
):
    api, make_token, store, main, jwks_client = api_context
    captured = {}
    sources = [{"source": "Brochure-EMSI.pdf", "page": 4, "score": 0.9}]
    monkeypatch.setattr(
        main,
        "chat",
        lambda request: captured.update(request=request)
        or main.ChatResponse(
            answer="Rabat (Brochure-EMSI.pdf, page 4).", sources=sources, images=[]
        ),
    )

    response = api.post(
        f"/api/conversations/{CONVERSATION_ID}/chat",
        headers={"Authorization": f"Bearer {make_token()}"},
        json={
            "question": "Et celui de Rabat ?",
            "request_id": str(REQUEST_ID),
            "include_images": False,
        },
    )
    jwks_client.close()

    assert response.status_code == 200
    assert response.json() == {
        "answer": "Rabat (Brochure-EMSI.pdf, page 4).",
        "sources": sources,
        "images": [],
    }
    assert captured["request"].question == "Et celui de Rabat ?"
    assert captured["request"].history == [
        main.ConversationTurn(role="user", content="Quels campus ?"),
        main.ConversationTurn(
            role="assistant", content="Rabat et Casablanca. [[REF:A]]"
        ),
    ]
    assert store.events[0] == ("assert_owned", CONVERSATION_ID, "owner-123")
    assert store.events[3][0] == "save_user"
    assert store.events[3][1] == "owner-123"
    assert store.events[3][2] == REQUEST_ID
    assert store.events.index(next(event for event in store.events if event[0] == "save_user")) < store.events.index(
        next(event for event in store.events if event[0] == "save_assistant")
    )
    assert ("touch", "Et celui de Rabat") in store.events
    assert store.events.index(next(event for event in store.events if event[0] == "touch")) < store.events.index(
        next(event for event in store.events if event[0] == "save_assistant")
    )


def test_persistent_chat_saves_and_returns_verified_image_caption_and_page(api_context, monkeypatch):
    api, make_token, store, main, jwks_client = api_context
    images = [{
        "url": "/images/Brochure-EMSI/images/page_4_image_1.jpeg",
        "source": "Brochure-EMSI.pdf",
        "page": 4,
        "caption": "Campus EMSI de Rabat",
        "caption_verified": True,
    }]
    monkeypatch.setattr(
        main,
        "chat",
        lambda request: main.ChatResponse(
            answer="Photo légendée.",
            sources=[{"source": "Brochure-EMSI.pdf", "page": 4}],
            images=images,
        ),
    )
    response = api.post(
        f"/api/conversations/{CONVERSATION_ID}/chat",
        headers={"Authorization": f"Bearer {make_token()}"},
        json={
            "question": "Montre une photo du campus de Rabat",
            "request_id": str(REQUEST_ID),
            "include_images": True,
        },
    )
    jwks_client.close()

    assert response.status_code == 200
    assert response.json()["images"] == images
    assert store.saved_images == images


def test_persistent_chat_requires_authentication_and_returns_404_for_other_owner(
    api_context
):
    api, make_token, _, _, jwks_client = api_context
    path = f"/api/conversations/{CONVERSATION_ID}/chat"
    anonymous = api.post(path, json={"question": "test", "request_id": str(REQUEST_ID)})
    other_user = api.post(
        path,
        headers={"Authorization": f"Bearer {make_token(subject='other-user')}"},
        json={"question": "test", "request_id": str(REQUEST_ID)},
    )
    jwks_client.close()
    assert anonymous.status_code == 401
    assert other_user.status_code == 404


def test_persistent_chat_rejects_invalid_bearer_token(api_context):
    api, _, _, _, jwks_client = api_context
    response = api.post(
        f"/api/conversations/{CONVERSATION_ID}/chat",
        headers={"Authorization": "Bearer not-a-signed-jwt"},
        json={"question": "test", "request_id": str(REQUEST_ID)},
    )
    jwks_client.close()
    assert response.status_code == 401
    assert "not-a-signed-jwt" not in response.text


def test_persistent_chat_rejects_client_supplied_identity(api_context):
    api, make_token, store, _, jwks_client = api_context
    response = api.post(
        f"/api/conversations/{CONVERSATION_ID}/chat",
        headers={"Authorization": f"Bearer {make_token()}"},
        json={
            "question": "test",
            "request_id": str(REQUEST_ID),
            "user_id": "attacker-chosen-id",
            "history": [],
        },
    )
    jwks_client.close()
    assert response.status_code == 422
    assert store.events == []


def test_persistent_chat_sends_at_most_five_prior_exchanges(api_context, monkeypatch):
    api, make_token, store, main, jwks_client = api_context
    store.history_rows = [
        {
            "role": "user" if index % 2 == 0 else "assistant",
            "content": f"turn-{index}",
            "sequence_number": index,
            "client_request_id": f"00000000-0000-4000-8000-{index:012d}",
        }
        for index in range(12)
    ]
    captured = {}

    def fake_chat(request):
        captured["history"] = request.history
        return main.ChatResponse(answer="bounded", sources=[], images=[])

    monkeypatch.setattr(main, "chat", fake_chat)
    response = api.post(
        f"/api/conversations/{CONVERSATION_ID}/chat",
        headers={"Authorization": f"Bearer {make_token()}"},
        json={"question": "new question", "request_id": str(REQUEST_ID)},
    )
    jwks_client.close()
    assert response.status_code == 200
    assert len(captured["history"]) == 10
    assert [turn.content for turn in captured["history"]] == [
        f"turn-{index}" for index in range(2, 12)
    ]


def test_same_request_id_returns_persisted_reply_without_rag(api_context, monkeypatch):
    api, make_token, store, main, jwks_client = api_context
    store.reply = {
        "content": "Réponse déjà sauvegardée.",
        "sources": [{"source": "Brochure-EMSI.pdf", "page": 8}],
        "images": [],
    }
    store.user_questions[str(REQUEST_ID)] = "Rejouer"
    monkeypatch.setattr(
        main,
        "chat",
        lambda _: pytest.fail("RAG should not run again for a completed request."),
    )
    response = api.post(
        f"/api/conversations/{CONVERSATION_ID}/chat",
        headers={"Authorization": f"Bearer {make_token()}"},
        json={"question": "Rejouer", "request_id": str(REQUEST_ID)},
    )
    jwks_client.close()
    assert response.status_code == 200
    assert response.json()["answer"] == "Réponse déjà sauvegardée."
    assert response.json()["sources"][0]["page"] == 8
    assert all(event[0] != "save_user" for event in store.events)


def test_request_id_cannot_be_reused_for_a_different_question(api_context):
    api, make_token, store, _, jwks_client = api_context
    store.reply = {"content": "Saved answer", "sources": [], "images": []}
    store.user_questions[str(REQUEST_ID)] = "Original question"
    response = api.post(
        f"/api/conversations/{CONVERSATION_ID}/chat",
        headers={"Authorization": f"Bearer {make_token()}"},
        json={"question": "Different question", "request_id": str(REQUEST_ID)},
    )
    jwks_client.close()
    assert response.status_code == 409
    assert "Original question" not in response.text


def test_storage_failure_keeps_question_and_returns_retryable_error(api_context, monkeypatch):
    api, make_token, store, main, jwks_client = api_context
    store.raise_on_assistant_save = True
    monkeypatch.setattr(
        main,
        "chat",
        lambda _: main.ChatResponse(answer="Une réponse", sources=[], images=[]),
    )
    response = api.post(
        f"/api/conversations/{CONVERSATION_ID}/chat",
        headers={"Authorization": f"Bearer {make_token()}"},
        json={"question": "Question conservée", "request_id": str(REQUEST_ID)},
    )
    jwks_client.close()
    assert response.status_code == 503
    assert "same request_id" in response.json()["detail"]
    assert any(event[0] == "save_user" for event in store.events)

"""Server-side persistence for authenticated chat turns via Supabase PostgREST.

The service-role key is intentionally confined to the backend environment. Each
operation still scopes records to the user ID from a cryptographically verified
Supabase access token; request payloads never supply an owner ID.
"""

from __future__ import annotations

import os
from functools import lru_cache
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx


class ConversationStoreConfigurationError(RuntimeError):
    pass


class ConversationStoreUnavailable(RuntimeError):
    pass


class ConversationNotFound(LookupError):
    pass


class ConversationRequestConflict(ValueError):
    """An idempotency key was already used for a different question."""


class SupabaseConversationStore:
    def __init__(
        self,
        project_url: str,
        service_role_key: str,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        if not project_url.startswith("https://") or not service_role_key:
            raise ConversationStoreConfigurationError(
                "Supabase database access is not configured."
            )
        self._base_url = f"{project_url.rstrip('/')}/rest/v1"
        self._key = service_role_key
        self._http = client or httpx.Client(timeout=8.0, follow_redirects=False)

    def _request(
        self,
        method: str,
        resource: str,
        *,
        params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
        prefer: str | None = None,
    ) -> list[dict[str, Any]]:
        headers = {
            "apikey": self._key,
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        try:
            response = self._http.request(
                method,
                f"{self._base_url}/{resource}",
                params=params,
                json=body,
                headers=headers,
            )
            response.raise_for_status()
            if not response.content:
                return []
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            # Deliberately omit headers, request bodies and upstream response text.
            raise ConversationStoreUnavailable(
                "Supabase conversation storage is unavailable."
            ) from exc
        if isinstance(payload, dict):
            return [payload]
        if not isinstance(payload, list) or not all(
            isinstance(row, dict) for row in payload
        ):
            raise ConversationStoreUnavailable(
                "Supabase returned an invalid conversation response."
            )
        return payload

    def assert_owned(self, conversation_id: UUID, user_id: str) -> None:
        rows = self._request(
            "GET",
            "conversations",
            params={
                "id": f"eq.{conversation_id}",
                "user_id": f"eq.{user_id}",
                "select": "id",
                "limit": "1",
            },
        )
        if not rows:
            raise ConversationNotFound("Conversation not found.")

    def load_recent_messages(
        self, conversation_id: UUID, user_id: str, *, limit: int = 10
    ) -> list[dict[str, Any]]:
        rows = self._request(
            "GET",
            "messages",
            params={
                "conversation_id": f"eq.{conversation_id}",
                "user_id": f"eq.{user_id}",
                "select": "role,content,sequence_number,client_request_id",
                "order": "sequence_number.desc",
                "limit": str(min(max(limit, 0), 10) + 1),
            },
        )
        return list(reversed(rows))

    def get_reply(
        self, conversation_id: UUID, user_id: str, request_id: UUID
    ) -> dict[str, Any] | None:
        rows = self._request(
            "GET",
            "messages",
            params={
                "conversation_id": f"eq.{conversation_id}",
                "user_id": f"eq.{user_id}",
                "client_request_id": f"eq.{request_id}",
                "role": "eq.assistant",
                "select": "content,sources,images",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    def get_user_message(
        self, conversation_id: UUID, user_id: str, request_id: UUID
    ) -> dict[str, Any] | None:
        rows = self._request(
            "GET",
            "messages",
            params={
                "conversation_id": f"eq.{conversation_id}",
                "user_id": f"eq.{user_id}",
                "client_request_id": f"eq.{request_id}",
                "role": "eq.user",
                "select": "content,images",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    def assert_request_question(
        self,
        conversation_id: UUID,
        user_id: str,
        request_id: UUID,
        question: str,
    ) -> None:
        rows = self._request(
            "GET",
            "messages",
            params={
                "conversation_id": f"eq.{conversation_id}",
                "user_id": f"eq.{user_id}",
                "client_request_id": f"eq.{request_id}",
                "role": "eq.user",
                "select": "content",
                "limit": "1",
            },
        )
        if not rows:
            raise ConversationStoreUnavailable(
                "The request could not be confirmed in conversation storage."
            )
        if rows[0].get("content") != question:
            raise ConversationRequestConflict(
                "The request ID was already used for another question."
            )

    def save_user_message(
        self,
        conversation_id: UUID,
        user_id: str,
        request_id: UUID,
        content: str,
        images: list[dict[str, Any]] | None = None,
    ) -> None:
        rows = self._request(
            "POST",
            "messages",
            params={"on_conflict": "conversation_id,client_request_id,role"},
            body={
                "conversation_id": str(conversation_id),
                "user_id": user_id,
                "role": "user",
                "content": content,
                "images": images or [],
                "client_request_id": str(request_id),
            },
            prefer="resolution=ignore-duplicates,return=representation",
        )
        if not rows:
            self.assert_request_question(
                conversation_id, user_id, request_id, content
            )

    def save_assistant_message(
        self,
        conversation_id: UUID,
        user_id: str,
        request_id: UUID,
        content: str,
        sources: list[dict[str, Any]],
        images: list[dict[str, Any]],
    ) -> dict[str, Any]:
        rows = self._request(
            "POST",
            "messages",
            params={"on_conflict": "conversation_id,client_request_id,role"},
            body={
                "conversation_id": str(conversation_id),
                "user_id": user_id,
                "role": "assistant",
                "content": content,
                "sources": sources,
                "images": images,
                "client_request_id": str(request_id),
            },
            prefer="resolution=ignore-duplicates,return=representation",
        )
        if rows:
            return rows[0]
        existing = self.get_reply(conversation_id, user_id, request_id)
        if existing is None:
            raise ConversationStoreUnavailable(
                "The generated answer could not be confirmed as saved."
            )
        return existing

    def touch_conversation(
        self,
        conversation_id: UUID,
        user_id: str,
        *,
        proposed_title: str,
    ) -> None:
        self._request(
            "PATCH",
            "conversations",
            params={
                "id": f"eq.{conversation_id}",
                "user_id": f"eq.{user_id}",
            },
            body={"updated_at": datetime.now(timezone.utc).isoformat()},
            prefer="return=minimal",
        )
        # Only a still-default title is changed, so manual renames are preserved.
        self._request(
            "PATCH",
            "conversations",
            params={
                "id": f"eq.{conversation_id}",
                "user_id": f"eq.{user_id}",
                "title": "eq.Nouvelle conversation",
            },
            body={"title": proposed_title},
            prefer="return=minimal",
        )


@lru_cache(maxsize=1)
def get_conversation_store() -> SupabaseConversationStore:
    project_url = os.getenv("SUPABASE_URL", "").strip()
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    return SupabaseConversationStore(project_url, service_role_key)

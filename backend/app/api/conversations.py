"""Authenticated chat endpoint that persists turns for an owned conversation."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.api.auth import require_authenticated_user
from app.security.supabase_jwt import SupabaseIdentity
from app.services.conversation_store import (
    ConversationNotFound,
    ConversationRequestConflict,
    ConversationStoreConfigurationError,
    ConversationStoreUnavailable,
    get_conversation_store,
)


router = APIRouter(prefix="/conversations", tags=["conversations"])


class PersistentChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    request_id: UUID
    use_llm: bool = True
    include_images: bool = False

    class Config:
        extra = "forbid"


def _title_from_question(question: str) -> str:
    normalized = " ".join(question.split()).strip(" .?!")
    if len(normalized) > 80:
        normalized = f"{normalized[:77].rstrip()}…"
    return normalized or "Nouvelle conversation"


@router.post("/{conversation_id}/chat")
def chat_in_conversation(
    conversation_id: UUID,
    request: PersistentChatRequest,
    user: Annotated[SupabaseIdentity, Depends(require_authenticated_user)],
) -> dict[str, Any]:
    """Verify owner, persist the question, reuse RAG, then persist its answer.

    This endpoint takes no `user_id` and no client-supplied history. The only
    identity is the verified JWT subject; the last five exchanges are loaded
    from this owner's persisted rows.
    """
    from app.main import ChatRequest, ChatResponse, ConversationTurn, chat

    try:
        store = get_conversation_store()
        store.assert_owned(conversation_id, user.subject)

        previous_reply = store.get_reply(
            conversation_id, user.subject, request.request_id
        )
        if previous_reply is not None:
            store.assert_request_question(
                conversation_id,
                user.subject,
                request.request_id,
                request.question,
            )
            store.touch_conversation(
                conversation_id,
                user.subject,
                proposed_title=_title_from_question(request.question),
            )
            return ChatResponse(
                answer=str(previous_reply.get("content", "")),
                sources=previous_reply.get("sources") or [],
                images=previous_reply.get("images") or [],
            ).dict()

        persisted = store.load_recent_messages(
            conversation_id, user.subject, limit=10
        )
        history = [
            row
            for row in persisted
            if row.get("client_request_id") != str(request.request_id)
        ][-10:]
        store.save_user_message(
            conversation_id,
            user.subject,
            request.request_id,
            request.question,
        )
        # Keep a saved-but-interrupted question visible in the user's recent list.
        store.touch_conversation(
            conversation_id,
            user.subject,
            proposed_title=_title_from_question(request.question),
        )

        rag_request = ChatRequest(
            question=request.question,
            use_llm=request.use_llm,
            include_images=request.include_images,
            history=[
                ConversationTurn(role=row["role"], content=row["content"])
                for row in history
            ],
        )
        answer = chat(rag_request)
        saved_reply = store.save_assistant_message(
            conversation_id,
            user.subject,
            request.request_id,
            answer.answer,
            answer.sources,
            answer.images,
        )
        return ChatResponse(
            answer=str(saved_reply.get("content", answer.answer)),
            sources=saved_reply.get("sources") or answer.sources,
            images=saved_reply.get("images") or answer.images,
        ).dict()
    except ConversationNotFound as exc:
        raise HTTPException(status_code=404, detail="Conversation not found.") from exc
    except ConversationRequestConflict as exc:
        raise HTTPException(
            status_code=409,
            detail="This request ID has already been used for another question.",
        ) from exc
    except ConversationStoreConfigurationError as exc:
        raise HTTPException(
            status_code=503,
            detail="Persistent conversations are not configured on the server.",
        ) from exc
    except ConversationStoreUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Conversation storage is temporarily unavailable. The question may "
                "already be saved; retry with the same request_id."
            ),
        ) from exc


@router.post("/{conversation_id}/vision")
def chat_with_uploaded_image(
    conversation_id: UUID,
    question: str = Form(min_length=1, max_length=1000),
    request_id: UUID = Form(),
    image: UploadFile = File(),
    user: SupabaseIdentity = Depends(require_authenticated_user),
) -> dict[str, Any]:
    """Analyze one private image for an authenticated conversation owner."""
    from app.services.vision_service import (
        VisionInputError,
        VisionProviderError,
        generate_image_answer,
        get_private_image_storage,
        image_metadata,
        max_upload_bytes,
        validate_image,
    )
    from app.main import ChatResponse

    try:
        store = get_conversation_store()
        store.assert_owned(conversation_id, user.subject)
        data = image.file.read(max_upload_bytes() + 1)
        if len(data) > max_upload_bytes():
            raise HTTPException(status_code=413, detail="L'image dépasse la taille maximale autorisée.")
        try:
            mime_type, extension, _width, _height = validate_image(data)
        except VisionInputError as exc:
            status = 413 if "taille maximale" in str(exc) else 415
            raise HTTPException(status_code=status, detail=str(exc)) from exc

        digest_metadata = image_metadata(
            user_id=user.subject,
            conversation_id=conversation_id,
            request_id=request_id,
            extension=extension,
            mime_type=mime_type,
            data=data,
        )
        previous_user_message = store.get_user_message(
            conversation_id, user.subject, request_id
        )
        if previous_user_message is not None:
            if previous_user_message.get("content") != question:
                raise ConversationRequestConflict("Request ID conflict.")
            old_images = previous_user_message.get("images") or []
            old_image = old_images[0] if old_images else {}
            if old_image.get("sha256") != digest_metadata["sha256"]:
                raise ConversationRequestConflict("Request ID conflict.")
            metadata = old_image
        previous_reply = store.get_reply(conversation_id, user.subject, request_id)
        if previous_reply is not None:
            if previous_user_message is None:
                raise ConversationRequestConflict("Request ID conflict.")
            store.assert_request_question(
                conversation_id, user.subject, request_id, question
            )
            return ChatResponse(
                answer=str(previous_reply.get("content", "")),
                sources=previous_reply.get("sources") or [],
                images=previous_reply.get("images") or [],
            ).dict()
        if previous_user_message is None:
            metadata = digest_metadata
            storage = get_private_image_storage()
            storage.upload(metadata, data)
            try:
                store.save_user_message(
                    conversation_id,
                    user.subject,
                    request_id,
                    question,
                    images=[metadata],
                )
            except Exception:
                try:
                    storage.delete(metadata)
                except Exception:
                    import logging

                    logging.getLogger("emsi-chatbot.vision").warning(
                        "Failed to remove an upload after message persistence failed."
                    )
                raise

        store.touch_conversation(
            conversation_id, user.subject, proposed_title=_title_from_question(question)
        )
        answer = generate_image_answer(question, data, mime_type)
        sources: list[dict[str, Any]] = []
        normalized_question = question.casefold()
        asks_about_brochure = any(
            marker in normalized_question
            for marker in ("brochure", "documents emsi", "document emsi", "selon l'emsi")
        )
        if asks_about_brochure:
            from app.main import ChatRequest, chat

            try:
                documentary = chat(
                    ChatRequest(
                        question=question,
                        use_llm=True,
                        include_images=False,
                    )
                )
                answer = (
                    f"Observation de l’image : {answer}\n\n"
                    f"Vérification dans la brochure EMSI : {documentary.answer}"
                )
                sources = documentary.sources
            except HTTPException:
                answer += "\n\nLa vérification dans la brochure est temporairement indisponible."
        saved_reply = store.save_assistant_message(
            conversation_id, user.subject, request_id, answer, sources, []
        )
        return ChatResponse(
            answer=str(saved_reply.get("content", answer)),
            sources=saved_reply.get("sources") or [],
            images=saved_reply.get("images") or [],
        ).dict()
    except HTTPException:
        raise
    except ConversationNotFound as exc:
        raise HTTPException(status_code=404, detail="Conversation not found.") from exc
    except ConversationRequestConflict as exc:
        raise HTTPException(
            status_code=409,
            detail="This request ID has already been used for another question or image.",
        ) from exc
    except VisionProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except ConversationStoreUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail="Conversation storage is temporarily unavailable; retry with the same request ID.",
        ) from exc
    except (ConversationStoreConfigurationError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Private image storage is not configured or is temporarily unavailable.",
        ) from exc

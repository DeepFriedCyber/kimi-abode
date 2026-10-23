"""FastAPI router for chat endpoints (JSON and Server-Sent Events)."""

from __future__ import annotations

import json
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter()


class ChatMessageIn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4_000)


class ChatRequestIn(BaseModel):
    messages: list[ChatMessageIn] = Field(min_length=1, max_length=50)
    property_id: int | None = Field(default=None, ge=1)


# Module-level fallback so tests can inject a service without an app instance.
_chat_service = None


def set_chat_service(service) -> None:
    global _chat_service
    _chat_service = service


def _get_chat_service(request: Request):
    service = getattr(request.app.state, "chat_service", None) or _chat_service
    if not service:
        raise HTTPException(status_code=503, detail="Chat service not initialised")
    return service


async def _load_property_context(request: Request, property_id: int | None) -> dict | None:
    if not property_id:
        return None

    pool = getattr(request.app.state, "pool", None)
    try:
        from ..property_service import resolve_property

        record, _ = await resolve_property(pool, property_id)
    except Exception as exc:  # noqa: BLE001 - chat still works without context
        logger.warning("[Chat] property context lookup failed: %s", exc)
        return None

    return {"property": record} if record else None


@router.post("/chat")
async def chat_endpoint(payload: ChatRequestIn, request: Request):
    """Return a complete chat response."""
    service = _get_chat_service(request)
    context = await _load_property_context(request, payload.property_id)

    messages = [message.model_dump() for message in payload.messages]
    response = await service.chat(
        user_message=messages[-1]["content"], property_context=context
    )

    has_llm = not type(service.llm).__name__.startswith("ChatFallback")
    return {"response": response, "has_llm": has_llm}


@router.post("/chat/stream")
async def chat_stream_endpoint(payload: ChatRequestIn, request: Request):
    """Stream chat responses as Server-Sent Events.

    Wire format: `data: {"chunk": "..."}\\n\\n`, terminated by `data: [DONE]`.
    """
    service = _get_chat_service(request)
    context = await _load_property_context(request, payload.property_id)
    messages = [message.model_dump() for message in payload.messages]

    async def event_stream():
        try:
            async for chunk in service.stream(messages, property_context=context):
                yield f"data: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"
        except Exception as exc:  # noqa: BLE001 - report, do not kill the connection
            logger.error("[Chat] stream failed: %s", exc, exc_info=True)
            yield f"data: {json.dumps({'error': 'chat stream failed'})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

"""FastAPI router for chat endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

router = APIRouter()


def _get_chat_service(request: Request):
    """Resolve the chat service from FastAPI app state (avoids global mutation)."""
    chat_svc = request.app.state.get("chat_service")
    if not chat_svc:
        raise HTTPException(status_code=503, detail="Chat service not initialised")
    return chat_svc


@router.post("/chat")
async def chat_endpoint(
    body: dict,
    request: Request,
):
    """Handle a chat request."""
    svc = _get_chat_service(request)

    messages = body.get("messages", [])
    if not messages:
        raise HTTPException(status_code=400, detail="messages array is required")

    last_message = messages[-1]
    user_message = last_message.get("content")
    if not user_message:
        raise HTTPException(status_code=400, detail="last message must contain 'content'")

    property_id = body.get("property_id")

    property_context = None
    if property_id:
        try:
            pool = request.app.state.pool
            if pool:
                async with pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT * FROM properties WHERE id = $1", property_id,
                    )
                    if row:
                        property_context = {"property": dict(row)}
        except Exception:
            pass

    response = await svc.chat(user_message=user_message, property_context=property_context)
    return {"response": response}


@router.post("/chat/stream")
async def chat_stream_endpoint(
    body: dict,
    request: Request,
):
    """Stream chat responses for real-time UI."""
    svc = _get_chat_service(request)

    messages = body.get("messages", [])
    if not messages:
        raise HTTPException(status_code=400, detail="messages array is required")

    return StreamingResponse(
        svc.stream(messages, property_context=None),
        media_type="text/event-stream",
    )

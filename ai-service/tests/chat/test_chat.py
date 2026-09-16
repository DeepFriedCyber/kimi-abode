"""Tests for chat service."""

from __future__ import annotations

import pytest


class TestChatService:
    """Tests for the ChatService class."""

    @pytest.mark.asyncio
    async def test_chat_stream(self):
        from app.chat.service import ChatService, _NoLLM

        llm = _NoLLM()
        service = ChatService(llm)

        response = await service.chat("What is the stamp duty on £300k?")
        assert isinstance(response, str)
        assert len(response) > 0


class TestChatRouter:
    """Tests for the chat router endpoint."""

    @pytest.mark.asyncio
    async def test_chat_endpoint_not_ready(self):
        from app.routers.chat import set_chat_service, chat_endpoint

        # Uninitialised — should raise 503
        with pytest.raises(Exception):  # 503 HTTPException
            await chat_endpoint({"messages": [{"role": "user", "content": "hi"}]})

    def test_set_chat_service(self):
        from app.routers.chat import set_chat_service, _chat_service
        from app.chat.service import ChatService, _NoLLM

        llm = _NoLLM()
        service = ChatService(llm)
        set_chat_service(service)
        # After setting, _chat_service should be available

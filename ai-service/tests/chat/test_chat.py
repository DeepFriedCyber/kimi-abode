"""Tests for chat service."""

from __future__ import annotations

import pytest


class TestChatService:
    """Tests for the ChatService class."""

    @pytest.mark.asyncio
    async def test_chat_stream(self):
        from app.chat.service import ChatService, ChatFallbackLLM

        llm = ChatFallbackLLM()
        service = ChatService(llm)

        response = await service.chat("What is the stamp duty on £300k?")
        assert isinstance(response, str)
        assert len(response) > 0


class TestChatRouter:
    """Tests for the chat router endpoint."""

    @pytest.mark.asyncio
    async def test_chat_endpoint_not_ready(self):
        from app.routers.chat import chat_endpoint, _chat_service
        import app.routers.chat as chat_mod

        # Ensure module-level service is cleared for this test
        chat_mod._chat_service = None

        mock_request = type("R", (), {"app": type("A", (), {"state": type("S", (), {})()})()})()
        # When no service is set, the resolver should raise HTTPException(503)
        with pytest.raises(Exception):  # 503 HTTPException
            await chat_endpoint({"messages": [{"role": "user", "content": "hi"}]}, mock_request)

    def test_set_chat_service(self):
        from app.routers.chat import set_chat_service
        import app.routers.chat as chat_mod
        from app.chat.service import ChatService, ChatFallbackLLM

        llm = ChatFallbackLLM()
        service = ChatService(llm)
        set_chat_service(service)
        assert chat_mod._chat_service is service

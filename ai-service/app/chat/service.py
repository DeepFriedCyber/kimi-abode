"""Chat service — context-aware property chat with Anthropic integration."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Optional


class ChatService:
    """Property-focused chat service.

    Provides context-aware responses using:
    - LLM (Anthropic) for natural conversation
    - Search/reasoning tools for property-specific queries
    - Cache for repeated queries (~70% API cost reduction target)
    """

    def __init__(self, llm, cache=None, parse_fn=None, search_fn=None):
        self.llm = llm
        self.cache = cache
        self.parse_fn = parse_fn or (lambda q: {})
        self.search_fn = search_fn or (lambda **kw: [])

    async def stream(self, messages: list[dict], property_context: dict | None = None):
        """Stream chat responses. Yields partial chunks."""

        # Check cache first
        user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        if self.cache:
            cached = await self.cache.get(user_msg)
            if cached and cached.get("hit_count", 0) > 0:
                yield cached["response"]
                return

        # Build system prompt with property context
        system_prompt = self._build_system(property_context or {})

        # Call LLM (with fallback)
        response = await self._call_llm(messages, system_prompt)

        if self.cache:
            await self.cache.put(user_msg, {"response": response})

        yield response

    async def chat(self, user_message: str, property_context: dict | None = None) -> str:
        """Non-streaming chat (use for simple responses)."""
        response_chunks: list[str] = []
        async for chunk in self.stream(
            [{"role": "user", "content": user_message}],
            property_context,
        ):
            response_chunks.append(chunk)
        if not response_chunks:
            return "(No response from chat service)"
        return "".join(response_chunks)

    def _build_system(self, context: dict) -> str:
        props = f"Current property: {json.dumps(context.get('property', {}))}" if context.get("property") else ""
        return (
            "You are an AI property assistant for the UK market. "
            "Help users with property searches, stamp duty calculations, mortgages, "
            "and local area information.\n"
            f"{props}\n\nRules:\n- Be accurate with UK property data\n"
            "- Stamp duty rates: 0% up to £250k (first home), 5% above £250k\n"
            "- Always cite your assumptions\n- Recommend viewing for final decisions"
        )

    async def _call_llm(self, messages, system_prompt):
        """Call the LLM with fallback chain."""
        try:
            return await self.llm.stream(messages, system_prompt)
        except Exception as e:
            return f"(LLM unavailable: {e}) Here's what I know from my database:"


class AnthropicChatLLM:
    """Anthropic Claude integration for property chat."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client = None  # lazy

    async def stream(self, messages, system_prompt):
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.AsyncAnthropic(api_key=self.api_key)
            except ImportError:
                raise RuntimeError("anthropic package not installed")

        # Build message list
        content = [{"role": m["role"], "content": m["content"]} for m in messages]

        response = await self._client.messages.create(
            model="claude-sonnet-4-20250514",
            system=system_prompt,
            messages=content,
            max_tokens=1024,
            temperature=0.3,
        )

        return response.content[0].text if response.content else ""


class ChatFallbackLLM:
    """Graceful degradation when no LLM API key is configured."""

    async def stream(self, messages, system_prompt=""):
        user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        return (
            f"Chat needs ANTHROPIC_API_KEY configured. But I can still help with:\n"
            f"- Property search: \"{user_msg}\"\n"
            f"- Stamp duty calculations\n- Mortgage estimates\n"
            f"- POI information near properties"
        )

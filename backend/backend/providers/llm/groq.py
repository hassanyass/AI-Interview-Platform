"""Groq adapter for the LLM port (OpenAI-compatible chat completions)."""
from __future__ import annotations

import logging
from typing import Sequence

from groq import AsyncGroq

from backend.core.metrics import timed_provider_call
from backend.providers.llm.base import ChatMessage, LLMProvider

logger = logging.getLogger(__name__)


class GroqLLMProvider(LLMProvider):
    def __init__(
        self,
        *,
        api_key: str,
        default_model: str,
        base_url: str | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not configured in backend settings")
        self.default_model = default_model
        # Async client: no thread hop, and the request never blocks the
        # ASGI event loop (the production symptom the old sync-in-thread
        # wrapper existed to avoid).
        # The SDK appends "/openai/v1" to base_url itself. Accept the
        # fully-qualified form too (the pre-H1-B raw-HTTP setting used it)
        # instead of producing ".../openai/v1/openai/v1/..." -- a real
        # regression the legacy suite caught in H2-A2.
        if base_url:
            base_url = base_url.rstrip("/")
            if base_url.endswith("/openai/v1"):
                base_url = base_url[: -len("/openai/v1")]
        self._client = AsyncGroq(
            api_key=api_key,
            base_url=base_url or None,
            timeout=timeout_seconds,
            max_retries=max_retries,
        )

    @timed_provider_call("groq", "complete_json")
    async def complete_json(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str | None = None,
        temperature: float,
        max_tokens: int | None = None,
    ) -> str:
        kwargs = dict(
            messages=list(messages),
            model=model or self.default_model,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        completion = await self._client.chat.completions.create(**kwargs)
        content = completion.choices[0].message.content
        if not content:
            raise RuntimeError("Groq returned an empty completion")
        return content

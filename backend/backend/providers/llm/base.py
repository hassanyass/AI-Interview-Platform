"""LLM port: chat completion that must return a JSON document."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence, TypedDict


class ChatMessage(TypedDict):
    role: str      # "system" | "user" | "assistant"
    content: str


class LLMProvider(ABC):
    """Every backend LLM use today is the same shape: a system prompt, a
    user payload, JSON mode, read back one string and ``json.loads`` it.
    Callers keep their own prompts and parsing; the adapter owns the wire."""

    @abstractmethod
    async def complete_json(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str | None = None,
        temperature: float,
        max_tokens: int | None = None,
    ) -> str:
        """Return the raw JSON text of the assistant message. ``model=None``
        means the adapter's configured default. Raises on transport or
        provider errors; never returns a partial/empty document silently."""
        raise NotImplementedError

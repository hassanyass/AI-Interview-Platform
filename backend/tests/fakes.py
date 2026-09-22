"""Test doubles for the provider ports (backend/backend/providers)."""
from __future__ import annotations

import json
from typing import Any, Sequence

from backend.providers.email.base import EmailMessage, EmailProvider, EmailSendResult
from backend.providers.llm.base import ChatMessage, LLMProvider
from backend.providers.storage.base import ObjectStorage, S3Destination


class FakeLLMProvider(LLMProvider):
    """Returns a canned JSON document and records every call.

    ``reply`` may be a dict (serialised for you), a string, or an exception
    instance to raise -- the shape the old tests obtained by mocking the
    Groq SDK object / the httpx client."""

    def __init__(self, reply: Any = None) -> None:
        self.reply = reply if reply is not None else {}
        self.calls: list[dict] = []

    async def complete_json(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str | None = None,
        temperature: float,
        max_tokens: int | None = None,
    ) -> str:
        self.calls.append({"messages": list(messages), "model": model, "temperature": temperature, "max_tokens": max_tokens})
        if isinstance(self.reply, BaseException):
            raise self.reply
        return self.reply if isinstance(self.reply, str) else json.dumps(self.reply)

    @property
    def last_messages(self) -> list[ChatMessage]:
        return self.calls[-1]["messages"]


class FakeEmailProvider(EmailProvider):
    name = "fake"

    def __init__(self, sent: bool = True) -> None:
        self.sent_flag = sent
        self.messages: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> EmailSendResult:
        self.messages.append(message)
        return EmailSendResult(sent=self.sent_flag, provider=self.name, message_id="m-1" if self.sent_flag else None)


class MemoryStorage(ObjectStorage):
    def __init__(self, configured: bool = True) -> None:
        self._configured = configured
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []

    @property
    def configured(self) -> bool:
        return self._configured

    async def put(self, key: str, data: bytes, *, content_type: str) -> None:
        self.objects[key] = data

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)
        self.deleted.append(key)

    def presign_get(self, key: str, *, ttl_seconds: int) -> str:
        return f"memory://{key}?ttl={ttl_seconds}"

    def egress_destination(self) -> S3Destination:
        return S3Destination(access_key="ak", secret="sk", bucket="b", endpoint="https://s3.test")

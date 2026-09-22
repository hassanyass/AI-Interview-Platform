"""Per-request correlation id.

Accepts an inbound ``X-Request-ID`` (so the agent -- or a proxy -- can
propagate its own) or mints a UUID4, stores it on ``request.state`` and
echoes it on every response. Error bodies carry it (core/errors.py);
structured logging binds it in H3.
"""
from __future__ import annotations

import re
import uuid

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

HEADER = "x-request-id"
_SAFE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def get_request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


class RequestIdMiddleware:
    """Pure ASGI (no BaseHTTPMiddleware) so streaming and background tasks
    behave exactly as before."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        inbound = None
        for name, value in scope.get("headers", []):
            if name == HEADER.encode():
                candidate = value.decode("latin-1")
                if _SAFE.match(candidate):
                    inbound = candidate
                break
        request_id = inbound or uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                if not any(name == HEADER.encode() for name, _ in headers):
                    headers.append((HEADER.encode(), request_id.encode("latin-1")))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_header)

"""Typed application errors and the one response shape every error takes.

docs/production-hardening-plan.md H2-A1. Raise an ``AppError`` subclass from
services and routers; ``install_exception_handlers`` (main.py) turns it --
and every legacy ``HTTPException``, validation error and unhandled exception
-- into the same problem-details body (RFC 7807 members plus ``request_id``):

    {"type": "about:blank", "title": "Conflict", "status": 409,
     "detail": "<human-readable message>", "instance": "/api/v1/...",
     "request_id": "…", "code": "<optional machine code>"}

``detail`` keeps exactly the value the code raised with: the frontend
(lib/api.ts), the agent (persistence.py) and the test suites all read it.
The media type stays ``application/json`` on purpose -- the agent parses
error bodies with aiohttp's ``resp.json()``, which rejects
``application/problem+json``.
"""
from __future__ import annotations

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

import sqlalchemy.exc

from backend.core.db_errors import exhaustion_source, is_connection_exhaustion
from backend.core.request_id import HEADER, get_request_id

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base class. ``status`` is the HTTP status, ``detail`` the message the
    client sees, ``code`` an optional stable machine-readable identifier."""

    status: int = 500
    code: str | None = None

    def __init__(
        self, detail: str | None = None, *, code: str | None = None, status: int | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.detail = detail or HTTPStatus(status or self.status).phrase
        if code is not None:
            self.code = code
        if status is not None:
            self.status = status
        # Some rejections carry a header the client is meant to act on --
        # 429's Retry-After. Copied onto the response by the handler below.
        self.headers = headers or {}
        super().__init__(self.detail)


class BadRequest(AppError):
    status = 400


class Unauthorized(AppError):
    status = 401


class Forbidden(AppError):
    status = 403


class NotFound(AppError):
    status = 404


class Conflict(AppError):
    status = 409


class PayloadTooLarge(AppError):
    status = 413


class ValidationFailed(AppError):
    status = 422


class UpstreamError(AppError):
    """A provider (LLM, storage, realtime) answered with a failure."""
    status = 502


class ServiceUnavailable(AppError):
    status = 503


class UpstreamTimeout(AppError):
    status = 504


class TooManyRequests(AppError):
    """Rate limited (H5-B). Always raised with a Retry-After header."""
    status = 429


def problem(request: Request, status: int, detail: Any, *, code: str | None = None) -> JSONResponse:
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": HTTPStatus(status).phrase,
        "status": status,
        "detail": detail,
        "instance": request.url.path,
        "request_id": get_request_id(request),
    }
    if code:
        body["code"] = code
    response = JSONResponse(status_code=status, content=body)
    # Set here as well as in RequestIdMiddleware: the unhandled-exception
    # handler runs in Starlette's outermost ServerErrorMiddleware, above ours,
    # so its response would otherwise leave without the header.
    if body["request_id"]:
        response.headers[HEADER] = body["request_id"]
    return response


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        response = problem(request, exc.status, exc.detail, code=exc.code)
        for key, value in getattr(exc, "headers", {}).items():
            response.headers[key] = value
        return response

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Every legacy `raise HTTPException(...)` gets the shared shape;
        # `detail` is passed through untouched (str, list or dict).
        response = problem(request, exc.status_code, exc.detail)
        headers = getattr(exc, "headers", None)
        if headers:
            for k, v in headers.items():
                response.headers[k] = v
        return response

    @app.exception_handler(HTTPException)
    async def _fastapi_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        return await _http_exception(request, exc)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        # FastAPI's list-of-errors `detail` is kept: lib/api.ts joins the
        # `msg` fields of a list detail.
        return problem(request, 422, exc.errors())

    @app.exception_handler(sqlalchemy.exc.SQLAlchemyError)
    async def _db_error(request: Request, exc: sqlalchemy.exc.SQLAlchemyError) -> JSONResponse:
        # H5-B left this open: the connection pooler refusing another client
        # reached the caller as a 500, which says "this server is broken"
        # when the truth is "busy, try again". Only exhaustion is softened;
        # every other SQLAlchemy failure falls through to the 500 below,
        # because a 503 invites a retry loop against a broken database.
        if not is_connection_exhaustion(exc):
            return await _unhandled(request, exc)
        logger.warning(
            "Database connections exhausted (%s) on %s %s (request_id=%s)",
            exhaustion_source(exc), request.method, request.url.path, get_request_id(request),
        )
        response = problem(
            request, 503,
            "The service is busy. Please retry in a moment.",
            code="db_unavailable",
        )
        response.headers["Retry-After"] = "5"
        return response

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Unhandled error on %s %s (request_id=%s)",
            request.method, request.url.path, get_request_id(request),
        )
        return problem(
            request, 500,
            "Internal server error. Quote the request_id when reporting this.",
            code="internal_error",
        )

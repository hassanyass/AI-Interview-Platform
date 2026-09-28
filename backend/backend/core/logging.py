"""One logging setup for the backend (H3).

Every record carries the correlation context of the request it happened in
-- ``request_id`` (RequestIdMiddleware), ``session_id`` (bound by the
routes that know it) -- injected by a logging Filter, so none of the
existing ``logger.info(...)`` calls change. Two formats:

- ``json``: one JSON object per line (``ts, level, logger, message,
  service, env, request_id, session_id, ...extra``) for production and
  any log pipeline;
- ``text``: ``ts level [logger] message  request_id=… session_id=…`` for
  a terminal.

The same formatter is applied to uvicorn's own loggers so access lines
match and carry the ids too. Structured extras go through ``extra=``
(standard logging) and land as top-level JSON keys.
"""
from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

SERVICE = "backend"

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
session_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("session_id", default=None)

_STANDARD_ATTRS = set(vars(logging.makeLogRecord({})).keys()) | {"message", "asctime"}


def bind_session(session_id: Any) -> contextvars.Token:
    """Attach a session id to every log line for the rest of this task/request."""
    return session_id_var.set(str(session_id) if session_id is not None else None)


class ContextFilter(logging.Filter):
    def __init__(self, environment: str) -> None:
        super().__init__()
        self.environment = environment

    def filter(self, record: logging.LogRecord) -> bool:
        record.service = SERVICE
        record.env = self.environment
        record.request_id = request_id_var.get()
        record.session_id = session_id_var.get()
        return True


def _extras(record: logging.LogRecord) -> dict[str, Any]:
    return {k: v for k, v in record.__dict__.items()
            if k not in _STANDARD_ATTRS and k not in ("service", "env", "request_id", "session_id") and not k.startswith("_")}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        body: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": getattr(record, "service", SERVICE),
            "env": getattr(record, "env", None),
            "request_id": getattr(record, "request_id", None),
            "session_id": getattr(record, "session_id", None),
        }
        body.update(_extras(record))
        if record.exc_info:
            body["exception"] = self.formatException(record.exc_info)
        return json.dumps(body, default=str, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)s [%(name)s] %(message)s", datefmt="%H:%M:%S")

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        ctx = []
        if getattr(record, "request_id", None):
            ctx.append(f"request_id={record.request_id}")
        if getattr(record, "session_id", None):
            ctx.append(f"session_id={record.session_id}")
        for k, v in _extras(record).items():
            ctx.append(f"{k}={v}")
        return f"{base}  {' '.join(ctx)}" if ctx else base


def configure_logging(*, log_format: str, level: str, environment: str) -> None:
    """Idempotent: replaces the root handlers so re-import / reload never
    doubles lines. Also captures uvicorn's loggers."""
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if log_format == "json" else TextFormatter())
    handler.addFilter(ContextFilter(environment))
    root.addHandler(handler)
    root.setLevel(level.upper())
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True
    logging.getLogger("uvicorn.access").setLevel(level.upper())


def uvicorn_log_config(log_format: str, level: str, environment: str) -> dict:
    """dictConfig for `uvicorn --log-config` so the server's own startup
    and access lines use the same formatter (and carry the ids)."""
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {"ctx": {"()": "backend.core.logging.ContextFilter", "environment": environment}},
        "formatters": {"app": {"()": "backend.core.logging.JsonFormatter" if log_format == "json" else "backend.core.logging.TextFormatter"}},
        "handlers": {"default": {"class": "logging.StreamHandler", "stream": "ext://sys.stdout", "formatter": "app", "filters": ["ctx"]}},
        "root": {"handlers": ["default"], "level": level.upper()},
        "loggers": {
            "uvicorn": {"handlers": [], "propagate": True},
            "uvicorn.error": {"handlers": [], "propagate": True},
            "uvicorn.access": {"handlers": [], "propagate": True, "level": level.upper()},
        },
    }

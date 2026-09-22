"""Agent logging (H3): one handler, one format, session context on every line.

livekit-agents installs its own root handler in ``cli.run_app`` (colored in
``dev``, JSON in ``start``). The worker used to add a second one through
``logging.basicConfig`` -- every line came out twice, and in production in
two formats. Now: ``configure_worker_logging`` runs *after* the SDK's setup
(from ``prewarm``/``entrypoint``, both inside the job process) and

- keeps exactly one stream handler on the root logger,
- in ``json`` mode replaces its formatter with ours (same shape as the
  backend's: ts, level, logger, message, service, env, session_id,
  agent_id, job_id, ...extra), in ``text`` mode keeps the SDK's readable
  colored formatter but appends the context fields,
- adds a Filter that stamps ``session_id`` / ``agent_id`` / ``job_id`` from
  contextvars onto every record so none of the existing calls change.

``bind_session`` is called at the top of ``_run_session``.
"""
from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

SERVICE = "agent"

session_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("session_id", default=None)
agent_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("agent_id", default=None)
job_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("job_id", default=None)

_STANDARD_ATTRS = set(vars(logging.makeLogRecord({})).keys()) | {"message", "asctime"}
_CONTEXT_KEYS = ("service", "env", "session_id", "agent_id", "job_id")


def bind_session(session_id: str | None, agent_id: str | None = None, job_id: str | None = None) -> None:
    session_id_var.set(session_id)
    if agent_id is not None:
        agent_id_var.set(agent_id)
    if job_id is not None:
        job_id_var.set(job_id)


class ContextFilter(logging.Filter):
    def __init__(self, environment: str) -> None:
        super().__init__()
        self.environment = environment

    def filter(self, record: logging.LogRecord) -> bool:
        record.service = SERVICE
        record.env = self.environment
        record.session_id = session_id_var.get()
        record.agent_id = agent_id_var.get()
        record.job_id = job_id_var.get()
        return True


def _extras(record: logging.LogRecord) -> dict[str, Any]:
    out = {}
    for k, v in record.__dict__.items():
        if k in _STANDARD_ATTRS or k in _CONTEXT_KEYS or k.startswith("_"):
            continue
        # the SDK's own JSON formatter packs extras under "extra"; unpack them
        if k == "extra" and isinstance(v, dict):
            out.update(v)
        else:
            out[k] = v
    return out


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        body: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": SERVICE,
            "env": getattr(record, "env", None),
            "session_id": getattr(record, "session_id", None),
            "agent_id": getattr(record, "agent_id", None),
            "job_id": getattr(record, "job_id", None),
        }
        body.update(_extras(record))
        if record.exc_info:
            body["exception"] = self.formatException(record.exc_info)
        return json.dumps(body, default=str, ensure_ascii=False)


class ContextSuffixFormatter(logging.Formatter):
    """Wraps the SDK's colored dev formatter (or a plain one) and appends
    the context fields so a terminal still shows which session a line is."""

    def __init__(self, inner: logging.Formatter | None) -> None:
        super().__init__()
        self.inner = inner or logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s", datefmt="%H:%M:%S")

    def format(self, record: logging.LogRecord) -> str:
        base = self.inner.format(record)
        ctx = [f"{k}={getattr(record, k)}" for k in ("session_id", "agent_id") if getattr(record, k, None)]
        return f"{base}  {' '.join(ctx)}" if ctx else base


def configure_worker_logging(*, log_format: str, level: str, environment: str) -> None:
    """Idempotent. Call after the SDK's setup_logging (i.e. from inside the
    job process); safe to call several times."""
    root = logging.getLogger()
    # Only plain StreamHandlers are ours to dedupe (the SDK's and the old
    # basicConfig one). Subclasses -- pytest's capture, file handlers -- are
    # someone else's and stay.
    stream_handlers = [h for h in root.handlers if type(h) is logging.StreamHandler]
    if not stream_handlers:
        h = logging.StreamHandler(sys.stdout)
        root.addHandler(h)
        stream_handlers = [h]
    keep = stream_handlers[0]
    for h in stream_handlers[1:]:
        root.removeHandler(h)
    if not any(isinstance(f, ContextFilter) for f in keep.filters):
        keep.addFilter(ContextFilter(environment))
    if log_format == "json":
        if not isinstance(keep.formatter, JsonFormatter):
            keep.setFormatter(JsonFormatter())
    else:
        if not isinstance(keep.formatter, ContextSuffixFormatter):
            keep.setFormatter(ContextSuffixFormatter(keep.formatter))
    root.setLevel(level.upper())
    # Windows consoles default to cp1252; a CV or question with a character
    # outside it made the stream handler raise on every such line. Replace
    # rather than crash the handler (live finding, 2026-09-16).
    stream = getattr(keep, "stream", None)
    if stream is not None and hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(errors="replace")
        except (ValueError, AttributeError):
            pass

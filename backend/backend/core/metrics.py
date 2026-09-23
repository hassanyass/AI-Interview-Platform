"""Prometheus metrics for the backend (H3).

``GET /metrics`` (main.py) serves the default registry. Unauthenticated by
design -- protect it at the network layer (docs/handover/observability.md).

Instrumentation points:
- HTTP: ``MetricsMiddleware`` (pure ASGI) -- requests total and latency by
  route template + status;
- providers: ``timed_provider_call`` decorator on the adapters' methods;
- sweep, readiness, background tasks: counters/gauges updated where those
  things happen.
"""
from __future__ import annotations

import functools
import time
from typing import Awaitable, Callable, TypeVar

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.types import ASGIApp, Message, Receive, Scope, Send

http_requests_total = Counter(
    "http_requests_total", "HTTP requests", ["method", "route", "status"]
)
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds", "HTTP request latency", ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
)
provider_call_duration_seconds = Histogram(
    "provider_call_duration_seconds", "External provider call latency", ["provider", "op"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120),
)
provider_call_failures_total = Counter(
    "provider_call_failures_total", "External provider call failures", ["provider", "op"]
)
sweep_runs_total = Counter(
    "sweep_runs_total", "Idle-disconnect sweep iterations", ["outcome"]  # ran | skipped_locked | failed
)
sweep_finalized_total = Counter("sweep_finalized_total", "Sessions auto-finalized by the sweep")
ready_check_failures_total = Counter("ready_check_failures_total", "Readiness probe failures", ["check"])
rate_limit_rejections_total = Counter("rate_limit_rejections_total", "Requests refused by a rate limit", ["scope"])
background_tasks_pending = Gauge("background_tasks_pending", "Tracked fire-and-forget tasks in flight")
# H2-F: the durable queue (models/task.py). Distinct from the gauge above,
# which counts in-process fire-and-forget asyncio tasks.
task_queue_depth = Gauge("task_queue_depth", "Tasks in the durable queue", ["status"])  # QUEUED | RUNNING
task_queue_oldest_age_seconds = Gauge("task_queue_oldest_age_seconds", "Age of the oldest queued task")
tasks_total = Counter("tasks_total", "Finished tasks", ["kind", "outcome"])  # succeeded | failed
task_duration_seconds = Histogram(
    "task_duration_seconds", "Task handler runtime", ["kind"],
    buckets=(0.5, 1, 2.5, 5, 10, 20, 30, 60, 120, 300),
)

F = TypeVar("F", bound=Callable[..., Awaitable])


def timed_provider_call(provider: str, op: str):
    """Decorator for async adapter methods: latency histogram + failure counter."""
    def deco(fn: F) -> F:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return await fn(*args, **kwargs)
            except Exception:
                provider_call_failures_total.labels(provider, op).inc()
                raise
            finally:
                provider_call_duration_seconds.labels(provider, op).observe(time.perf_counter() - start)
        return wrapper  # type: ignore[return-value]
    return deco


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST


class MetricsMiddleware:
    """Counts and times every HTTP request. The route label is the matched
    path template (``/api/v1/admin/jobs/{job_id}``), never the raw path, so
    ids do not explode the cardinality; unmatched paths are labelled
    ``<unmatched>``."""

    def __init__(self, app: ASGIApp, *, routes_provider: Callable[[], list] | None = None) -> None:
        self.app = app
        self._routes_provider = routes_provider
        self._templates: dict[object, str] | None = None

    def _template_for(self, scope: Scope) -> str:
        # Starlette puts the matched endpoint (not the route) in the scope;
        # map endpoint -> path template once from the app's route table.
        endpoint = scope.get("endpoint")
        if endpoint is None:
            return "<unmatched>"
        if self._templates is None and self._routes_provider is not None:
            self._templates = {}
            self._collect(self._routes_provider(), "")
        return (self._templates or {}).get(endpoint, "<unmatched>")

    def _collect(self, routes, prefix: str) -> None:
        # Routers added with include_router appear in app.routes as an
        # _IncludedRouter (FastAPI >= 0.135): no endpoint/path of its own,
        # but the original router and the prefix it was mounted under.
        for route in routes:
            inner = getattr(route, "original_router", None)
            if inner is not None:
                ctx = getattr(route, "include_context", None)
                self._collect(inner.routes, prefix + (getattr(ctx, "prefix", "") or ""))
                continue
            ep = getattr(route, "endpoint", None)
            path = getattr(route, "path", None)
            if ep is not None and path:
                self._templates[ep] = prefix + path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        method = scope.get("method", "?")
        start = time.perf_counter()
        status_holder = {"status": 500}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            if scope.get("path") == "/metrics":
                return
            template = self._template_for(scope)
            http_requests_total.labels(method, template, str(status_holder["status"])).inc()
            http_request_duration_seconds.labels(method, template).observe(time.perf_counter() - start)

import asyncio
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.sql import text

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from backend.core import background
from backend.core.config import settings
from backend.core.errors import install_exception_handlers
from backend.core.request_id import RequestIdMiddleware
from backend.db.session import engine
from backend.api.endpoints import profiles, resumes, interviews, livekit, internal, admin, invitations, public_invitations, public_apply
from backend.services.sessions.finalization import disconnect_auto_finalize_sweep_loop

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_disconnect_sweep_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Startup/shutdown (H2-B: `lifespan` replaces the deprecated on_event pair)."""
    global _disconnect_sweep_task
    logger.info("Application starting up...")
    # Session-finalization-contract fix (2026-09-01, see
    # docs/CURRENT_DECISIONS.md): backend-owned safety net for candidates
    # who disconnect and never resume -- see disconnect_auto_finalize_
    # sweep_loop's own docstring in services/sessions/finalization.py.
    _disconnect_sweep_task = asyncio.create_task(disconnect_auto_finalize_sweep_loop())
    try:
        yield
    finally:
        logger.info("Application shutting down...")
        if _disconnect_sweep_task:
            _disconnect_sweep_task.cancel()
        # Give in-flight fire-and-forget work (recording starts) a bounded
        # chance to finish before the pool goes away.
        await background.drain(timeout=5.0)
        await engine.dispose()


app = FastAPI(title="AI Interview Platform API", version=settings.APP_VERSION, lifespan=lifespan)

# One error body for every failure (core/errors.py).
install_exception_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)
# Correlation id on every request/response (core/request_id.py). Added last
# = outermost, so the id exists even for requests CORS itself answers.
app.add_middleware(RequestIdMiddleware)

# Include routers
app.include_router(profiles.router, prefix="/api/v1/profiles", tags=["profiles"])
app.include_router(resumes.router, prefix="/api/v1/resumes", tags=["resumes"])
app.include_router(interviews.router, prefix="/api/v1/interviews", tags=["interviews"])
app.include_router(livekit.router, prefix="/api/v1/livekit", tags=["livekit"])
app.include_router(internal.router, prefix="/api/v1/internal/interviews", tags=["internal"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])
app.include_router(invitations.router, prefix="/api/v1/admin", tags=["admin-invitations"])
app.include_router(public_invitations.router, prefix="/api/v1/invitations", tags=["public-invitations"])
app.include_router(public_apply.router, prefix="/api/v1/apply", tags=["public-apply"])


@app.get("/health")
async def health_check():
    """Liveness: the process is up and serving. Never touches the database
    (H2-B) -- a DB outage is a readiness problem, reported by /ready, not a
    reason for an orchestrator to restart the process."""
    return {
        "status": "ok",
        "service": "ai-interview-backend",
        "version": app.version,
        "environment": settings.ENVIRONMENT,
    }


@app.get("/ready")
async def readiness_check():
    """Readiness: 200 only when the database answers, else 503 with the
    reason -- what a load balancer / compose healthcheck should probe."""
    checks: dict[str, str] = {}
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:  # noqa: BLE001 -- any failure means not ready; the reason is reported, not raised
        logger.error("Readiness: database check failed: %s", e)
        checks["database"] = "error"
    ready = all(v == "ok" for v in checks.values())
    body = {"status": "ready" if ready else "not_ready", "checks": checks, "version": app.version}
    return JSONResponse(status_code=200 if ready else 503, content=body)


@app.get("/version")
async def version():
    return {"version": app.version}

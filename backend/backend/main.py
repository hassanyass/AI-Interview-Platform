from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.sql import text
from sqlalchemy.ext.asyncio import AsyncSession
import logging
import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from backend.core.config import settings
from backend.db.session import engine, get_db
from backend.api.endpoints import profiles, resumes, interviews, livekit, internal, admin, invitations, public_invitations, public_apply
from backend.api.endpoints.internal import disconnect_auto_finalize_sweep_loop

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Interview Platform API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

_disconnect_sweep_task: asyncio.Task | None = None

@app.on_event("startup")
async def startup_event():
    logger.info("Application starting up...")
    global _disconnect_sweep_task
    # Session-finalization-contract fix (2026-09-01, see
    # docs/CURRENT_DECISIONS.md): backend-owned safety net for candidates
    # who disconnect and never resume -- see disconnect_auto_finalize_
    # sweep_loop's own docstring in internal.py.
    _disconnect_sweep_task = asyncio.create_task(disconnect_auto_finalize_sweep_loop())

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Application shutting down...")
    if _disconnect_sweep_task:
        _disconnect_sweep_task.cancel()
    if engine:
        await engine.dispose()

@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    db_status = "disconnected"
    try:
        # Test database connection
        await db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        db_status = "error"
        
    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "service": "ai-interview-backend",
        "database": db_status,
        "version": app.version,
        "environment": settings.ENVIRONMENT
    }

@app.get("/version")
async def version():
    return {"version": app.version}

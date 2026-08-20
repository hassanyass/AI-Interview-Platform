from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.sql import text
from sqlalchemy.ext.asyncio import AsyncSession
import logging
import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.core.config import settings
from app.db.session import engine, get_db
from app.api.endpoints import profiles, resumes, interviews, livekit, internal

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

@app.on_event("startup")
async def startup_event():
    logger.info("Application starting up...")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Application shutting down...")
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

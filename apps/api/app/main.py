import sys
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Ensure project root and apps directory are in sys.path so background worker can import pipeline
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_APPS_DIR = Path(__file__).resolve().parents[2]
for _p in [str(_PROJECT_ROOT), str(_APPS_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import asyncio
from app.core.config import settings
from app.core.database import init_db
from app.api.v1.router import api_router
from app.services.queue_service import queue_service
from app.services.cleanup_service import storage_cleanup_service

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d) - %(message)s"
)
logger = logging.getLogger("soundsplit.api")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Database and Queue
    logger.info("Initializing SoundSplit Database tables...")
    init_db()
    logger.info("Connecting to Redis Queue & Event Bus...")
    await queue_service.connect()
    
    # Start intelligent storage cleanup background worker
    logger.info("Launching Intelligent Storage Cleanup worker...")
    cleanup_task = asyncio.create_task(storage_cleanup_service.periodic_cleanup_loop())
    
    yield
    
    # Shutdown
    logger.info("Shutting down SoundSplit API service...")
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Production-grade AI Audio & Music Source Separation Platform powered by Demucs v4",
    openapi_url="/api/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS Security Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=r"^https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security Headers Middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# Global Sanitized Error Handler (Prevent leaking stack traces or internal paths)
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": "An internal server error occurred while processing your request. Please try again later."
        }
    )

# Include API v1 Router
app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
def root():
    return {
        "app": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs": "/docs",
        "api_v1": settings.API_V1_STR
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

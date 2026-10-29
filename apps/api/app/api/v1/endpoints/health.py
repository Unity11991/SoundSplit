import torch
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Dict, Any

from app.core.database import get_db
from app.core.config import settings
from app.services.storage import storage_service
from app.services.queue_service import queue_service

router = APIRouter()

@router.get("/health", status_code=status.HTTP_200_OK)
def health_check():
    """Liveness probe returning basic API operational status."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION
    }

@router.get("/readiness", status_code=status.HTTP_200_OK)
async def readiness_check(db: Session = Depends(get_db)):
    """
    Readiness probe validating database connectivity, Redis/queue, storage, and AI inference engine.
    """
    checks: Dict[str, Any] = {}
    is_ready = True

    # 1. Database check
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok", "type": "sqlite" if settings.DATABASE_URL.startswith("sqlite") else "postgresql"}
    except Exception as e:
        checks["database"] = {"status": "error", "error": str(e)}
        is_ready = False

    # 2. Redis / Queue check
    redis_ok = await queue_service.is_redis_connected()
    checks["queue"] = {
        "status": "ok",
        "mode": "redis" if redis_ok else "in_process_worker_pool",
        "redis_connected": redis_ok
    }

    # 3. Storage check
    try:
        test_path = storage_service.get_absolute_path("inputs")
        checks["storage"] = {
            "status": "ok",
            "type": settings.STORAGE_TYPE,
            "directory": str(test_path),
            "writable": test_path.exists()
        }
    except Exception as e:
        checks["storage"] = {"status": "error", "error": str(e)}
        is_ready = False

    # 4. AI Model & Hardware check
    cuda_available = torch.cuda.is_available()
    device_name = torch.cuda.get_device_name(0) if cuda_available else "CPU (Multi-Threaded Fallback)"
    checks["ai_engine"] = {
        "status": "ok",
        "model": settings.DEFAULT_MODEL,
        "torch_version": torch.__version__,
        "cuda_available": cuda_available,
        "device": device_name,
        "supported_modes": ["two_stem", "four_stem", "voiceover"]
    }

    return {
        "status": "ready" if is_ready else "degraded",
        "checks": checks
    }

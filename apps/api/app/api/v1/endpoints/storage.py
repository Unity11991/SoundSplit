from fastapi import APIRouter, Depends, Query, status
from typing import Optional
from app.services.cleanup_service import storage_cleanup_service

router = APIRouter()

@router.get("/storage/status")
def get_storage_status():
    """
    Get real-time storage metrics, breakdown of inputs/outputs/exports,
    disk capacity, quota usage, and retention settings.
    """
    return storage_cleanup_service.get_storage_stats()

@router.post("/storage/cleanup")
def trigger_storage_cleanup(
    retention_hours: Optional[int] = Query(default=None, description="Custom retention threshold in hours"),
    force_orphans: bool = Query(default=True, description="Force delete unreferenced orphaned files")
):
    """
    Trigger intelligent storage cleanup:
    - Removes unreferenced / orphaned files
    - Removes incomplete or failed jobs
    - Enforces TTL retention policy
    - Enforces max storage quota via LRU eviction
    """
    result = storage_cleanup_service.run_intelligent_cleanup(
        retention_hours=retention_hours,
        force_orphans=force_orphans
    )
    return result

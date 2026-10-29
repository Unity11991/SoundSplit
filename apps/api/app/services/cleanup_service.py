import os
import shutil
import time
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List

from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.database import ProjectModel, SeparationModel, StemModel
from app.services.storage import storage_service

logger = logging.getLogger("soundsplit.cleanup")

class StorageCleanupService:
    def __init__(self):
        self.base_dir = storage_service.base_dir
        self.inputs_dir = self.base_dir / "inputs"
        self.outputs_dir = self.base_dir / "outputs"
        self.exports_dir = self.base_dir / "exports"

    def get_storage_stats(self) -> Dict[str, Any]:
        """Calculate live disk and directory storage metrics."""
        def dir_stats(p: Path):
            if not p.exists():
                return 0, 0
            files = [f for f in p.rglob("*") if f.is_file() and f.name != ".gitkeep"]
            size = sum(f.stat().st_size for f in files)
            return len(files), size

        inputs_count, inputs_bytes = dir_stats(self.inputs_dir)
        outputs_count, outputs_bytes = dir_stats(self.outputs_dir)
        exports_count, exports_bytes = dir_stats(self.exports_dir)
        total_bytes = inputs_bytes + outputs_bytes + exports_bytes

        # Host disk capacity
        try:
            total_disk, used_disk, free_disk = shutil.disk_usage(self.base_dir)
        except Exception:
            total_disk, used_disk, free_disk = 0, 0, 0

        # Project counts from DB
        project_count = 0
        oldest_project_str = None
        try:
            with SessionLocal() as db:
                project_count = db.query(ProjectModel).count()
                oldest = db.query(ProjectModel).order_by(ProjectModel.created_at.asc()).first()
                if oldest and oldest.created_at:
                    oldest_project_str = oldest.created_at.isoformat()
        except Exception as e:
            logger.warning(f"Failed to query project stats: {e}")

        return {
            "total_bytes": total_bytes,
            "total_mb": round(total_bytes / (1024 * 1024), 2),
            "max_storage_mb": settings.MAX_STORAGE_MB,
            "quota_used_percent": round((total_bytes / (settings.MAX_STORAGE_MB * 1024 * 1024)) * 100, 1) if settings.MAX_STORAGE_MB else 0,
            "breakdown": {
                "inputs": {"files": inputs_count, "mb": round(inputs_bytes / (1024 * 1024), 2)},
                "outputs": {"files": outputs_count, "mb": round(outputs_bytes / (1024 * 1024), 2)},
                "exports": {"files": exports_count, "mb": round(exports_bytes / (1024 * 1024), 2)},
            },
            "disk": {
                "total_gb": round(total_disk / (1024 ** 3), 2),
                "free_gb": round(free_disk / (1024 ** 3), 2),
            },
            "projects_count": project_count,
            "oldest_project_created_at": oldest_project_str,
            "retention_hours": settings.RETENTION_HOURS,
        }

    def delete_project_assets(self, project: ProjectModel, db: Session) -> int:
        """Thoroughly remove all storage assets belonging to a project."""
        freed = 0

        # 1. Delete all input media and associated preview / transcode files
        if project.original_storage_key:
            input_path = storage_service.get_absolute_path(project.original_storage_key)
            prefix = input_path.stem.split("_audio")[0]
            # Clean all files in inputs matching prefix (original upload, extracted wav, preview mp3)
            if self.inputs_dir.exists():
                for f in self.inputs_dir.glob(f"{prefix}*"):
                    if f.is_file() and f.name != ".gitkeep":
                        try:
                            freed += f.stat().st_size
                            f.unlink()
                        except Exception as e:
                            logger.warning(f"Error removing {f}: {e}")

        # 2. Delete all separation output folders
        for sep in project.separations:
            sep_dir = self.outputs_dir / sep.id
            if sep_dir.exists() and sep_dir.is_dir():
                try:
                    dir_size = sum(f.stat().st_size for f in sep_dir.rglob("*") if f.is_file())
                    freed += dir_size
                    shutil.rmtree(sep_dir)
                except Exception as e:
                    logger.warning(f"Error removing output dir {sep_dir}: {e}")

        # 3. Clean any exports
        if self.exports_dir.exists():
            for f in self.exports_dir.glob(f"*{project.id}*"):
                if f.is_file():
                    try:
                        freed += f.stat().st_size
                        f.unlink()
                    except Exception:
                        pass

        return freed

    def cleanup_orphaned_files(self, grace_period_seconds: Optional[int] = None) -> Dict[str, Any]:
        """
        Delete files on disk that have no record in the database.
        Files modified within grace_period_seconds are preserved to protect active uploads.
        """
        grace_period = grace_period_seconds if grace_period_seconds is not None else (settings.ORPHAN_GRACE_PERIOD_MINUTES * 60)
        cutoff_time = time.time() - grace_period
        freed_bytes = 0
        deleted_files = 0
        deleted_dirs = 0

        with SessionLocal() as db:
            # Collect known prefixes and paths
            projects = db.query(ProjectModel).all()
            separations = db.query(SeparationModel).all()

            known_input_prefixes = set()
            for p in projects:
                if p.original_storage_key:
                    k = Path(p.original_storage_key).stem.split("_audio")[0]
                    known_input_prefixes.add(k)
                    known_input_prefixes.add(p.id)

            known_sep_ids = {s.id for s in separations}

        # 1. Clean orphaned inputs
        if self.inputs_dir.exists():
            for f in self.inputs_dir.iterdir():
                if f.is_file() and f.name != ".gitkeep":
                    if f.stat().st_mtime < cutoff_time:
                        prefix = f.stem.split("_audio")[0].split(".")[0]
                        if prefix not in known_input_prefixes:
                            try:
                                freed_bytes += f.stat().st_size
                                f.unlink()
                                deleted_files += 1
                                logger.info(f"Cleaned orphaned input file: {f.name}")
                            except Exception as e:
                                logger.warning(f"Could not delete orphaned file {f}: {e}")

        # 2. Clean orphaned outputs
        if self.outputs_dir.exists():
            for d in self.outputs_dir.iterdir():
                if d.is_dir() and d.name != ".gitkeep":
                    if d.stat().st_mtime < cutoff_time:
                        if d.name not in known_sep_ids:
                            try:
                                size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
                                freed_bytes += size
                                shutil.rmtree(d)
                                deleted_dirs += 1
                                logger.info(f"Cleaned orphaned output folder: {d.name}")
                            except Exception as e:
                                logger.warning(f"Could not delete orphaned dir {d}: {e}")

        # 3. Clean exports older than 12 hours
        export_cutoff = time.time() - (12 * 3600)
        if self.exports_dir.exists():
            for f in self.exports_dir.iterdir():
                if f.is_file() and f.name != ".gitkeep" and f.stat().st_mtime < export_cutoff:
                    try:
                        freed_bytes += f.stat().st_size
                        f.unlink()
                        deleted_files += 1
                    except Exception:
                        pass

        return {
            "freed_bytes": freed_bytes,
            "deleted_files": deleted_files,
            "deleted_dirs": deleted_dirs
        }

    def cleanup_expired_projects(self, retention_hours: Optional[int] = None) -> Dict[str, Any]:
        """Delete projects and stems exceeding TTL retention period."""
        hours = retention_hours if retention_hours is not None else settings.RETENTION_HOURS
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        freed_bytes = 0
        projects_deleted = 0

        with SessionLocal() as db:
            # Query projects past expiration date OR older than retention cutoff
            expired_projects = db.query(ProjectModel).filter(
                (ProjectModel.expires_at.isnot(None) & (ProjectModel.expires_at < datetime.now(timezone.utc))) |
                (ProjectModel.created_at < cutoff)
            ).all()

            for proj in expired_projects:
                try:
                    freed = self.delete_project_assets(proj, db)
                    freed_bytes += freed
                    db.delete(proj)
                    projects_deleted += 1
                    logger.info(f"Auto-cleaned expired project: {proj.name} (ID: {proj.id})")
                except Exception as e:
                    logger.error(f"Failed deleting expired project {proj.id}: {e}")

            db.commit()

        return {
            "freed_bytes": freed_bytes,
            "projects_deleted": projects_deleted
        }

    def cleanup_failed_or_stuck_jobs(self, stuck_hours: Optional[int] = None) -> Dict[str, Any]:
        """Purge jobs that crashed or got stuck in incomplete states."""
        hours = stuck_hours if stuck_hours is not None else settings.FAILED_JOB_RETENTION_HOURS
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        freed_bytes = 0
        cleaned_count = 0

        with SessionLocal() as db:
            stuck_projects = db.query(ProjectModel).filter(
                ProjectModel.status.in_(["uploading", "failed"]),
                ProjectModel.created_at < cutoff
            ).all()

            for proj in stuck_projects:
                freed = self.delete_project_assets(proj, db)
                freed_bytes += freed
                db.delete(proj)
                cleaned_count += 1

            db.commit()

        return {
            "freed_bytes": freed_bytes,
            "stuck_projects_cleaned": cleaned_count
        }

    def enforce_storage_quota(self, max_storage_mb: Optional[int] = None, target_ratio: float = 0.75) -> Dict[str, Any]:
        """
        Enforce max storage limit via LRU eviction.
        If disk usage exceeds quota, first evicts auxiliary preview/transcode caches,
        then evicts oldest completed projects until below target_ratio.
        """
        limit_mb = max_storage_mb or settings.MAX_STORAGE_MB
        limit_bytes = limit_mb * 1024 * 1024
        target_bytes = int(limit_bytes * target_ratio)

        def current_size():
            return sum(f.stat().st_size for f in self.base_dir.rglob("*") if f.is_file() and f.name != ".gitkeep")

        total_freed = 0
        projects_evicted = 0

        # Check if over quota
        if current_size() <= limit_bytes:
            return {"freed_bytes": 0, "projects_evicted": 0}

        logger.warning(f"Storage exceeded quota ({current_size() / (1024*1024):.1f} MB > {limit_mb} MB). Triggering LRU eviction...")

        # Step 1: Prune transient preview and 320k transcodes older than 1 hour
        one_hour_ago = time.time() - 3600
        for f in self.outputs_dir.rglob("*.preview.mp3"):
            if f.is_file() and f.stat().st_mtime < one_hour_ago:
                try:
                    total_freed += f.stat().st_size
                    f.unlink()
                except Exception:
                    pass

        for f in self.outputs_dir.rglob("*.320k.mp3"):
            if f.is_file() and f.stat().st_mtime < one_hour_ago:
                try:
                    total_freed += f.stat().st_size
                    f.unlink()
                except Exception:
                    pass

        # Step 2: Evict oldest projects (LRU) until under target threshold
        if current_size() > target_bytes:
            with SessionLocal() as db:
                oldest_projects = db.query(ProjectModel).order_by(ProjectModel.created_at.asc()).all()
                for proj in oldest_projects:
                    freed = self.delete_project_assets(proj, db)
                    total_freed += freed
                    db.delete(proj)
                    projects_evicted += 1
                    logger.info(f"LRU quota evicted project: {proj.name}")
                    if current_size() <= target_bytes:
                        break
                db.commit()

        return {
            "freed_bytes": total_freed,
            "projects_evicted": projects_evicted
        }

    def ensure_upload_capacity(self, estimated_bytes: int):
        """Proactively evict space if an incoming upload would exceed the quota."""
        limit_bytes = settings.MAX_STORAGE_MB * 1024 * 1024
        current_bytes = sum(f.stat().st_size for f in self.base_dir.rglob("*") if f.is_file() and f.name != ".gitkeep")
        if (current_bytes + estimated_bytes) > limit_bytes:
            self.enforce_storage_quota(target_ratio=0.70)

    def run_intelligent_cleanup(
        self,
        retention_hours: Optional[int] = None,
        force_orphans: bool = True
    ) -> Dict[str, Any]:
        """Execute the full intelligent storage cleanup pipeline."""
        start_time = time.time()
        logger.info("Starting intelligent storage cleanup...")

        total_freed = 0
        details = {}

        # 1. Clean orphans
        if force_orphans or settings.AUTO_CLEAN_ORPHANS:
            orphan_res = self.cleanup_orphaned_files()
            total_freed += orphan_res["freed_bytes"]
            details["orphans"] = orphan_res

        # 2. Clean failed / stuck jobs
        failed_res = self.cleanup_failed_or_stuck_jobs()
        total_freed += failed_res["freed_bytes"]
        details["stuck_jobs"] = failed_res

        # 3. Clean expired projects (TTL)
        expired_res = self.cleanup_expired_projects(retention_hours=retention_hours)
        total_freed += expired_res["freed_bytes"]
        details["expired_projects"] = expired_res

        # 4. Enforce storage quota (LRU)
        quota_res = self.enforce_storage_quota()
        total_freed += quota_res["freed_bytes"]
        details["quota_eviction"] = quota_res

        stats_after = self.get_storage_stats()
        duration_ms = int((time.time() - start_time) * 1000)

        logger.info(
            f"Storage cleanup completed in {duration_ms}ms. "
            f"Freed {total_freed / (1024*1024):.2f} MB. Current usage: {stats_after['total_mb']} MB."
        )

        return {
            "success": True,
            "duration_ms": duration_ms,
            "freed_bytes": total_freed,
            "freed_mb": round(total_freed / (1024 * 1024), 2),
            "current_storage_mb": stats_after["total_mb"],
            "max_storage_mb": settings.MAX_STORAGE_MB,
            "details": details
        }

    async def periodic_cleanup_loop(self):
        """Asynchronous background worker running on a scheduled interval."""
        interval_seconds = max(300, settings.STORAGE_CLEANUP_INTERVAL_MINUTES * 60)
        logger.info(f"Storage cleanup worker initialized (Interval: {interval_seconds // 60}m, Retention: {settings.RETENTION_HOURS}h, Max: {settings.MAX_STORAGE_MB}MB)")

        # Initial pass 10 seconds after server boot
        await asyncio.sleep(10)
        try:
            self.run_intelligent_cleanup()
        except Exception as e:
            logger.warning(f"Error in initial storage cleanup pass: {e}")

        while True:
            try:
                await asyncio.sleep(interval_seconds)
                self.run_intelligent_cleanup()
            except asyncio.CancelledError:
                logger.info("Storage cleanup worker stopped.")
                break
            except Exception as e:
                logger.error(f"Error during periodic storage cleanup: {e}")

storage_cleanup_service = StorageCleanupService()

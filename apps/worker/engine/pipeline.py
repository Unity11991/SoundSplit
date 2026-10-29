import time
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Callable, Optional

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.database import SeparationModel, StemModel, ProjectModel
from app.services.storage import storage_service
from app.services.queue_service import queue_service
from apps.worker.engine.demucs_adapter import DemucsModelAdapter

logger = logging.getLogger("stemlab.pipeline")

# Singleton Demucs adapter instance to reuse loaded model across jobs
demucs_adapter = DemucsModelAdapter(model_name=settings.DEFAULT_MODEL)

class SeparationPipeline:
    def __init__(self, adapter=None):
        self.adapter = adapter or demucs_adapter

    async def execute_job(self, job_data: Dict[str, Any]):
        job_id = job_data["job_id"]
        project_id = job_data["project_id"]
        mode = job_data.get("mode", "two_stem")
        model_name = job_data.get("model_name", settings.DEFAULT_MODEL)

        start_time = time.time()
        logger.info(f"Starting separation job {job_id} for project {project_id} [Mode: {mode}]")

        db = SessionLocal()
        try:
            sep = db.query(SeparationModel).filter(SeparationModel.id == job_id).first()
            project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()

            if not sep or not project:
                logger.error(f"Job {job_id} or Project {project_id} not found in database")
                return

            sep.status = "processing"
            sep.stage = "Initializing AI model"
            sep.progress = 5
            sep.started_at = datetime.now(timezone.utc)
            project.status = "processing"
            db.commit()

            await queue_service.publish_event(job_id, {
                "job_id": job_id,
                "project_id": project_id,
                "status": "processing",
                "stage": "Initializing AI model",
                "progress": 5
            })

            # Get input audio file path
            input_audio_path = storage_service.get_absolute_path(project.original_storage_key)
            if not input_audio_path.exists():
                raise FileNotFoundError(f"Input audio file does not exist: {project.original_storage_key}")

            # Prepare job output directory
            output_dir = storage_service.get_absolute_path(f"outputs/{job_id}")
            output_dir.mkdir(parents=True, exist_ok=True)

            # Progress callback for real-time reporting (runs in worker thread)
            def progress_callback(prog: int, stage_desc: str):
                logger.info(f"Job {job_id} [{prog}%]: {stage_desc}")
                try:
                    with SessionLocal() as prog_db:
                        s = prog_db.query(SeparationModel).filter(SeparationModel.id == job_id).first()
                        if s:
                            s.progress = prog
                            s.stage = stage_desc
                            prog_db.commit()
                except Exception as ex:
                    logger.warning(f"Failed to update progress in db: {ex}")

            import asyncio
            # Execute real separation with Demucs asynchronously in a worker thread
            stems_dict = await asyncio.to_thread(
                self.adapter.separate,
                input_audio_path=input_audio_path,
                output_dir=output_dir,
                mode=mode,
                progress_callback=progress_callback
            )

            # Refresh outer session so it observes changes made by worker thread
            db.expire_all()

            # Clear any existing stems for this job to ensure idempotency
            db.query(StemModel).filter(StemModel.separation_id == job_id).delete()
            db.commit()

            stems_response = []
            for stem_type, stem_file in stems_dict.items():
                rel_storage_key = f"outputs/{job_id}/{stem_file.name}"
                file_size = stem_file.stat().st_size
                stem_record = StemModel(
                    separation_id=job_id,
                    stem_type=stem_type,
                    storage_key=rel_storage_key,
                    file_size_bytes=file_size,
                    duration_seconds=project.duration_seconds,
                    sample_rate=project.sample_rate,
                    format="wav"
                )
                db.add(stem_record)
                db.flush()

                stems_response.append({
                    "id": stem_record.id,
                    "separation_id": job_id,
                    "stem_type": stem_type,
                    "filename": stem_file.name,
                    "file_size_bytes": file_size,
                    "duration_seconds": project.duration_seconds,
                    "sample_rate": project.sample_rate,
                    "format": "wav"
                })

            elapsed = round(time.time() - start_time, 2)
            sep.status = "completed"
            sep.stage = "Separation completed successfully"
            sep.progress = 100
            sep.processing_time_seconds = elapsed
            sep.completed_at = datetime.now(timezone.utc)
            project.status = "completed"
            db.commit()

            logger.info(f"Job {job_id} completed successfully in {elapsed}s")

            await queue_service.publish_event(job_id, {
                "job_id": job_id,
                "project_id": project_id,
                "status": "completed",
                "stage": "Separation completed successfully",
                "progress": 100,
                "processing_time_seconds": elapsed,
                "stems": stems_response
            })

        except Exception as e:
            elapsed = round(time.time() - start_time, 2)
            logger.error(f"Separation job {job_id} failed: {e}", exc_info=True)
            db.rollback()
            try:
                sep = db.query(SeparationModel).filter(SeparationModel.id == job_id).first()
                if sep:
                    sep.status = "failed"
                    sep.stage = "Processing failed"
                    sep.error_code = "SEPARATION_FAILED"
                    sep.error_message = str(e)
                    sep.processing_time_seconds = elapsed
                    sep.completed_at = datetime.now(timezone.utc)
                project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
                if project:
                    project.status = "failed"
                db.commit()

                await queue_service.publish_event(job_id, {
                    "job_id": job_id,
                    "project_id": project_id,
                    "status": "failed",
                    "stage": "Processing failed",
                    "progress": 0,
                    "error_message": str(e)
                })
            except Exception as inner_e:
                logger.error(f"Failed to record failure in DB: {inner_e}")
        finally:
            db.close()

separation_pipeline = SeparationPipeline()
